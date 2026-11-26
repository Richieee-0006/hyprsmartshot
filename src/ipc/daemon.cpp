#include "ipc/daemon.hpp"
#include "core/actions.hpp"
#include "core/config.hpp"
#include "core/i18n.hpp"
#include "wayland/clipboard.hpp"

#include <algorithm>
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <malloc.h>
#include <poll.h>
#include <sys/inotify.h>
#include <sys/signalfd.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>

#include "cursor-shape-v1-client-protocol.h"
#include "fractional-scale-v1-client-protocol.h"
#include "viewporter-client-protocol.h"
#define namespace wl_namespace
#include "wlr-layer-shell-unstable-v1-client-protocol.h"
#undef namespace
#include "wlr-screencopy-unstable-v1-client-protocol.h"
#if HSS_HAVE_EXT_IMAGE_COPY_CAPTURE
#include "ext-image-capture-source-v1-client-protocol.h"
#include "ext-image-copy-capture-v1-client-protocol.h"
#endif
#if HSS_HAVE_EXT_DATA_CONTROL
#include "ext-data-control-v1-client-protocol.h"
#endif
#ifdef HSS_HAVE_LIBSYSTEMD
#include <systemd/sd-daemon.h>
#endif

namespace hss {

namespace fs = std::filesystem;

std::string Daemon::socket_path() {
    const char* xdg = std::getenv("XDG_RUNTIME_DIR");
    if (xdg && *xdg) return std::string(xdg) + "/hyprsmartshot.sock";
    return "/tmp/hyprsmartshot-" + std::to_string(getuid()) + ".sock";
}

long Daemon::read_self_rss_kb() {
    std::ifstream f("/proc/self/status");
    std::string line;
    while (std::getline(f, line)) {
        if (line.rfind("VmRSS:", 0) == 0) {
            try {
                return std::stol(line.substr(6));
            } catch (...) {
                return -1;
            }
        }
    }
    return -1;
}

std::optional<nlohmann::json> Daemon::send_command(const nlohmann::json& payload, int timeout_ms) {
    std::string path = socket_path();
    if (path.empty() || path.size() >= sizeof(sockaddr_un::sun_path)) return std::nullopt;

    int fd = ::socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (fd < 0) return std::nullopt;
    struct FdGuard { int fd; ~FdGuard() { if (fd >= 0) ::close(fd); } } guard{fd};

    sockaddr_un addr{};
    addr.sun_family = AF_UNIX;
    std::strncpy(addr.sun_path, path.c_str(), sizeof(addr.sun_path) - 1);
    if (::connect(fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
        return std::nullopt;
    }

    std::string msg = payload.dump() + "\n";
    size_t sent = 0;
    while (sent < msg.size()) {
        ssize_t n = ::send(fd, msg.data() + sent, msg.size() - sent, MSG_NOSIGNAL);
        if (n <= 0) return std::nullopt;
        sent += static_cast<size_t>(n);
    }

    std::string reply;
    char buf[4096];
    auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);
    while (true) {
        auto rem = std::chrono::duration_cast<std::chrono::milliseconds>(
                       deadline - std::chrono::steady_clock::now())
                       .count();
        if (rem <= 0) break;
        pollfd pfd{fd, POLLIN, 0};
        int pr = ::poll(&pfd, 1, static_cast<int>(rem));
        if (pr <= 0) break;
        ssize_t n = ::recv(fd, buf, sizeof(buf), 0);
        if (n <= 0) break;
        reply.append(buf, static_cast<size_t>(n));
        if (reply.find('\n') != std::string::npos) break;
    }

    if (reply.empty()) return std::nullopt;
    try {
        return nlohmann::json::parse(reply);
    } catch (...) {
        return std::nullopt;
    }
}

bool Daemon::ping() {
    auto res = send_command({{"cmd", "ping"}}, 500);
    return res && res->value("ok", false);
}

bool Daemon::notify_reload_config() {
    auto res = send_command({{"cmd", "reload-config"}}, 1000);
    return res && res->value("ok", false);
}

int Daemon::run_server(const std::string& explicit_config, const std::string& self_exe) {
    ::signal(SIGPIPE, SIG_IGN);

    // Prevent duplicate daemon instances
    if (ping()) {
        std::cerr << "hyprsmartshot daemon is already running at " << socket_path() << "\n";
        return 0;
    }

    std::string sock_path = socket_path();
    std::error_code ec;
    fs::remove(sock_path, ec);

    int srv_fd = ::socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (srv_fd < 0) {
        std::cerr << "Error: Failed to create daemon UNIX socket\n";
        return 1;
    }

    sockaddr_un addr{};
    addr.sun_family = AF_UNIX;
    std::strncpy(addr.sun_path, sock_path.c_str(), sizeof(addr.sun_path) - 1);
    if (::bind(srv_fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
        std::cerr << "Error: Failed to bind " << sock_path << "\n";
        ::close(srv_fd);
        return 1;
    }
    ::chmod(sock_path.c_str(), 0600);
    if (::listen(srv_fd, 8) < 0) {
        ::close(srv_fd);
        fs::remove(sock_path, ec);
        return 1;
    }

    // Persistent lightweight Wayland connection (registry + outputs + optional ext-data-control ONLY;
    // ZERO surfaces, ZERO shm buffers, ZERO GPU/EGL context while idle!)
    struct DaemonWl {
        WaylandSharedGlobals g;
        wl_registry* registry = nullptr;
#if HSS_HAVE_EXT_DATA_CONTROL
        ext_data_control_manager_v1* data_ctrl_mgr = nullptr;
#endif
        Clipboard clipboard;
    } wl;

    wl.g.display = wl_display_connect(nullptr);
    if (!wl.g.display) {
        std::cerr << "Error: Failed to connect to Wayland display\n";
        ::close(srv_fd);
        fs::remove(sock_path, ec);
        return 1;
    }
    wl.g.outputs.reserve(16);

    static const wl_output_listener out_l = {
        .geometry = [](void* data, wl_output*, int32_t x, int32_t y, int32_t, int32_t,
                       int32_t, const char*, const char*, int32_t tr) {
            auto* o = static_cast<WaylandOutput*>(data);
            o->x = x; o->y = y; o->transform = tr;
        },
        .mode = [](void* data, wl_output*, uint32_t flags, int32_t w, int32_t h, int32_t) {
            if (flags & WL_OUTPUT_MODE_CURRENT) {
                auto* o = static_cast<WaylandOutput*>(data);
                o->width = w; o->height = h;
            }
        },
        .done = [](void*, wl_output*) {},
        .scale = [](void* data, wl_output*, int32_t factor) {
            static_cast<WaylandOutput*>(data)->scale = factor;
        },
        .name = [](void* data, wl_output*, const char* name) {
            if (name) static_cast<WaylandOutput*>(data)->name = name;
        },
        .description = [](void*, wl_output*, const char*) {},
    };

    wl.registry = wl_display_get_registry(wl.g.display);
    static const wl_registry_listener reg_l = {
        .global = [](void* data, wl_registry* r, uint32_t name, const char* iface, uint32_t ver) {
            auto* d = static_cast<DaemonWl*>(data);
            auto& c = d->g;
            if (std::strcmp(iface, wl_compositor_interface.name) == 0) {
                c.compositor = static_cast<wl_compositor*>(
                    wl_registry_bind(r, name, &wl_compositor_interface, std::min(ver, 5u)));
            } else if (std::strcmp(iface, wl_shm_interface.name) == 0) {
                c.shm = static_cast<wl_shm*>(wl_registry_bind(r, name, &wl_shm_interface, 1));
            } else if (std::strcmp(iface, wl_seat_interface.name) == 0) {
                c.seat = static_cast<wl_seat*>(
                    wl_registry_bind(r, name, &wl_seat_interface, std::min(ver, 7u)));
            } else if (std::strcmp(iface, wl_output_interface.name) == 0 && c.outputs.size() < 16) {
                WaylandOutput wo;
                wo.global_name = name;
                wo.output = static_cast<wl_output*>(
                    wl_registry_bind(r, name, &wl_output_interface, std::min(ver, 4u)));
                c.outputs.push_back(wo);
                wl_output_add_listener(c.outputs.back().output, &out_l, &c.outputs.back());
            } else if (std::strcmp(iface, zwlr_layer_shell_v1_interface.name) == 0) {
                c.layer_shell = static_cast<zwlr_layer_shell_v1*>(
                    wl_registry_bind(r, name, &zwlr_layer_shell_v1_interface, std::min(ver, 4u)));
            } else if (std::strcmp(iface, zwlr_screencopy_manager_v1_interface.name) == 0) {
                c.wlr_screencopy_mgr = static_cast<zwlr_screencopy_manager_v1*>(
                    wl_registry_bind(r, name, &zwlr_screencopy_manager_v1_interface, std::min(ver, 3u)));
            } else if (std::strcmp(iface, wp_viewporter_interface.name) == 0) {
                c.viewporter = static_cast<wp_viewporter*>(
                    wl_registry_bind(r, name, &wp_viewporter_interface, 1));
            } else if (std::strcmp(iface, wp_fractional_scale_manager_v1_interface.name) == 0) {
                c.frac_mgr = static_cast<wp_fractional_scale_manager_v1*>(
                    wl_registry_bind(r, name, &wp_fractional_scale_manager_v1_interface, 1));
            } else if (std::strcmp(iface, wp_cursor_shape_manager_v1_interface.name) == 0) {
                c.cursor_mgr = static_cast<wp_cursor_shape_manager_v1*>(
                    wl_registry_bind(r, name, &wp_cursor_shape_manager_v1_interface, 1));
            }
#if HSS_HAVE_EXT_IMAGE_COPY_CAPTURE
            else if (std::strcmp(iface, ext_image_copy_capture_manager_v1_interface.name) == 0) {
                c.ext_capture_mgr = static_cast<ext_image_copy_capture_manager_v1*>(
                    wl_registry_bind(r, name, &ext_image_copy_capture_manager_v1_interface, 1));
            } else if (std::strcmp(iface, ext_output_image_capture_source_manager_v1_interface.name) == 0) {
                c.ext_source_mgr = static_cast<ext_output_image_capture_source_manager_v1*>(
                    wl_registry_bind(r, name, &ext_output_image_capture_source_manager_v1_interface, 1));
            }
#endif
#if HSS_HAVE_EXT_DATA_CONTROL
            else if (std::strcmp(iface, ext_data_control_manager_v1_interface.name) == 0) {
                d->data_ctrl_mgr = static_cast<ext_data_control_manager_v1*>(
                    wl_registry_bind(r, name, &ext_data_control_manager_v1_interface, 1));
            }
#endif
        },
        .global_remove = [](void* data, wl_registry*, uint32_t name) {
            auto* d = static_cast<DaemonWl*>(data);
            for (auto it = d->g.outputs.begin(); it != d->g.outputs.end(); ++it) {
                if (it->global_name == name) {
                    if (it->output) wl_output_destroy(it->output);
                    d->g.outputs.erase(it);
                    break;
                }
            }
        },
    };
    wl_registry_add_listener(wl.registry, &reg_l, &wl);
    wl_display_roundtrip(wl.g.display);
    wl_display_roundtrip(wl.g.display);

#if HSS_HAVE_EXT_DATA_CONTROL
    if (wl.data_ctrl_mgr && wl.g.seat) {
        wl.clipboard.attach_ext(wl.g.display, wl.data_ctrl_mgr, wl.g.seat);
        wl_display_flush(wl.g.display);
    }
#endif

    // Load cached config, i18n, and optional Satty theme sync
    fs::path data_dir = ConfigManager::resolve_data_dir(self_exe);
    nlohmann::json cfg;
    I18n i18n;
    auto reload_all = [&] {
        cfg = ConfigManager::load_config(explicit_config);
        std::string lang = cfg.value("language", std::string("en"));
        i18n.load(lang, ConfigManager::resolve_config_dir(explicit_config), data_dir);
        if (cfg.contains("theme") && cfg["theme"].is_object() && cfg["theme"].value("syncSatty", false)) {
            ConfigManager::export_satty_pywal_config(cfg);
        }
    };
    reload_all();

    // inotify watch on user config dir + Pywal cache dir for zero-cost live theme/config sync
    int inot_fd = ::inotify_init1(IN_NONBLOCK | IN_CLOEXEC);
    auto watch_dir_if_exists = [&](const fs::path& p) {
        if (inot_fd < 0 || p.empty()) return;
        std::error_code wec;
        if (fs::is_directory(p, wec)) {
            ::inotify_add_watch(inot_fd, p.c_str(), IN_CLOSE_WRITE | IN_MOVED_TO | IN_CREATE);
        }
    };
    watch_dir_if_exists(ConfigManager::resolve_config_dir(explicit_config));
    watch_dir_if_exists(ConfigManager::resolve_config_dir(explicit_config) / "config.d");
    if (cfg.contains("theme") && cfg["theme"].is_object()) {
        fs::path wal_p(ConfigManager::expand_home(cfg["theme"].value("pywalPath", std::string("~/.cache/wal/colors.json"))));
        watch_dir_if_exists(wal_p.parent_path());
    }

    // signalfd for clean shutdown & SIGCHLD reaping
    sigset_t mask;
    sigemptyset(&mask);
    sigaddset(&mask, SIGINT);
    sigaddset(&mask, SIGTERM);
    sigaddset(&mask, SIGCHLD);
    ::sigprocmask(SIG_BLOCK, &mask, nullptr);
    int sig_fd = ::signalfd(-1, &mask, SFD_NONBLOCK | SFD_CLOEXEC);

    auto start_tp = std::chrono::steady_clock::now();
    malloc_trim(0);

#ifdef HSS_HAVE_LIBSYSTEMD
    sd_notify(0, "READY=1");
#endif

    bool running = true;
    int wl_fd = wl_display_get_fd(wl.g.display);

    while (running) {
        while (wl_display_prepare_read(wl.g.display) != 0) {
            wl_display_dispatch_pending(wl.g.display);
        }
        if (wl_display_flush(wl.g.display) < 0 && errno != EAGAIN) {
            wl_display_cancel_read(wl.g.display);
            break;
        }

        pollfd pfds[4];
        pfds[0] = {wl_fd, POLLIN, 0};
        pfds[1] = {srv_fd, POLLIN, 0};
        pfds[2] = {inot_fd, POLLIN, 0};
        pfds[3] = {sig_fd, POLLIN, 0};

        int pr = ::poll(pfds, 4, -1);
        if (pr < 0) {
            wl_display_cancel_read(wl.g.display);
            if (errno == EINTR) continue;
            break;
        }

        if (pfds[0].revents & POLLIN) {
            if (wl_display_read_events(wl.g.display) < 0) break;
            wl_display_dispatch_pending(wl.g.display);
        } else {
            wl_display_cancel_read(wl.g.display);
            if (pfds[0].revents & (POLLERR | POLLHUP)) break;
        }

        // Handle signals
        if (sig_fd >= 0 && (pfds[3].revents & POLLIN)) {
            signalfd_siginfo info{};
            while (::read(sig_fd, &info, sizeof(info)) == sizeof(info)) {
                if (info.ssi_signo == SIGINT || info.ssi_signo == SIGTERM) {
                    running = false;
                } else if (info.ssi_signo == SIGCHLD) {
                    while (::waitpid(-1, nullptr, WNOHANG) > 0) {}
                }
            }
        }

        // Handle config/Pywal inotify updates
        if (inot_fd >= 0 && (pfds[2].revents & POLLIN)) {
            char ibuf[4096];
            while (::read(inot_fd, ibuf, sizeof(ibuf)) > 0) {}
            reload_all();
            malloc_trim(0);
        }

        // Handle incoming thin client IPC connections
        if (pfds[1].revents & POLLIN) {
            while (true) {
                int cfd = ::accept4(srv_fd, nullptr, nullptr, SOCK_CLOEXEC);
                if (cfd < 0) break;

                // Authenticate peer UID via SO_PEERCRED
                ucred cred{};
                socklen_t clen = sizeof(cred);
                if (::getsockopt(cfd, SOL_SOCKET, SO_PEERCRED, &cred, &clen) < 0 || cred.uid != geteuid()) {
                    ::close(cfd);
                    continue;
                }

                std::string raw;
                char rbuf[4096];
                pollfd cpfd{cfd, POLLIN, 0};
                if (::poll(&cpfd, 1, 500) > 0) {
                    ssize_t n = ::recv(cfd, rbuf, sizeof(rbuf), 0);
                    if (n > 0) raw.append(rbuf, static_cast<size_t>(n));
                }

                auto reply_json = [&](const nlohmann::json& j) {
                    std::string out = j.dump() + "\n";
                    (void)::send(cfd, out.data(), out.size(), MSG_NOSIGNAL);
                };

                try {
                    auto msg = nlohmann::json::parse(raw);
                    std::string cmd = msg.value("cmd", std::string());

                    if (cmd == "ping") {
                        reply_json({{"ok", true}, {"pid", getpid()}, {"rss_kb", read_self_rss_kb()}});
                    } else if (cmd == "status") {
                        auto up = std::chrono::duration_cast<std::chrono::seconds>(
                                      std::chrono::steady_clock::now() - start_tp)
                                      .count();
                        nlohmann::json outs = nlohmann::json::array();
                        for (const auto& o : wl.g.outputs) outs.push_back(o.name);
                        auto pal = ConfigManager::resolve_palette(cfg);
                        reply_json({
                            {"ok", true},
                            {"pid", getpid()},
                            {"uptime_s", up},
                            {"rss_kb", read_self_rss_kb()},
                            {"outputs", outs},
                            {"theme_source", pal.source},
                            {"language", i18n.lang()},
                        });
                    } else if (cmd == "reload-config") {
                        reload_all();
                        malloc_trim(0);
                        reply_json({{"ok", true}});
                    } else if (cmd == "quit") {
                        reply_json({{"ok", true}});
                        running = false;
                    } else if (cmd == "capture") {
                        CaptureRequest req;
                        req.mode = msg.value("mode", std::string("universal"));
                        req.preset = msg.value("preset", std::string());
                        req.explicit_config = msg.value("config", std::string());
                        req.ai_force = msg.value("ai_force", -1);
                        req.no_cv = msg.value("no_cv", false);
                        req.benchmark_exit = msg.value("benchmark_exit", false);

                        nlohmann::json run_cfg = req.explicit_config.empty()
                                                     ? cfg
                                                     : ConfigManager::load_config(req.explicit_config);
                        I18n run_i18n = i18n;
                        if (!req.explicit_config.empty()) {
                            run_i18n.load(run_cfg.value("language", std::string("en")),
                                          ConfigManager::resolve_config_dir(req.explicit_config), data_dir);
                        }

                        auto t0 = std::chrono::steady_clock::now();
                        bool quit_req = false;
                        int rc = OverlaySession::run(req, run_cfg, run_i18n, self_exe, &wl.g, &wl.clipboard, srv_fd, &quit_req);
                        if (quit_req) running = false;
                        double elapsed_ms = std::chrono::duration<double, std::milli>(
                                                std::chrono::steady_clock::now() - t0)
                                                .count();
                        malloc_trim(0);
                        reply_json({
                            {"ok", rc == 0},
                            {"rc", rc},
                            {"elapsed_ms", elapsed_ms},
                            {"post_rss_kb", read_self_rss_kb()},
                        });
                    } else {
                        reply_json({{"ok", false}, {"error", "Unknown command: " + cmd}});
                    }
                } catch (const std::exception& e) {
                    reply_json({{"ok", false}, {"error", e.what()}});
                }
                ::close(cfd);
            }
        }
    }

    wl.clipboard.detach();
    for (auto& o : wl.g.outputs) if (o.output) wl_output_destroy(o.output);
    if (wl.g.cursor_mgr) wp_cursor_shape_manager_v1_destroy(wl.g.cursor_mgr);
    if (wl.g.frac_mgr) wp_fractional_scale_manager_v1_destroy(wl.g.frac_mgr);
    if (wl.g.viewporter) wp_viewporter_destroy(wl.g.viewporter);
    if (wl.g.layer_shell) zwlr_layer_shell_v1_destroy(wl.g.layer_shell);
    if (wl.g.wlr_screencopy_mgr) zwlr_screencopy_manager_v1_destroy(wl.g.wlr_screencopy_mgr);
#if HSS_HAVE_EXT_IMAGE_COPY_CAPTURE
    if (wl.g.ext_capture_mgr) ext_image_copy_capture_manager_v1_destroy(wl.g.ext_capture_mgr);
    if (wl.g.ext_source_mgr) ext_output_image_capture_source_manager_v1_destroy(wl.g.ext_source_mgr);
#endif
#if HSS_HAVE_EXT_DATA_CONTROL
    if (wl.data_ctrl_mgr) ext_data_control_manager_v1_destroy(wl.data_ctrl_mgr);
#endif
    if (wl.g.seat) wl_seat_destroy(wl.g.seat);
    if (wl.g.shm) wl_shm_destroy(wl.g.shm);
    if (wl.g.compositor) wl_compositor_destroy(wl.g.compositor);
    if (wl.registry) wl_registry_destroy(wl.registry);
    if (wl.g.display) wl_display_disconnect(wl.g.display);
    if (inot_fd >= 0) ::close(inot_fd);
    if (sig_fd >= 0) ::close(sig_fd);
    ::close(srv_fd);
    fs::remove(sock_path, ec);
    return 0;
}

}  // namespace hss
