#include "vision/vision_bridge.hpp"

#include <csignal>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <filesystem>
#include <sys/wait.h>
#include <unistd.h>

namespace hss {

namespace fs = std::filesystem;

namespace {

using FreeStrFn = void (*)(char*);
using DetectCvFn = char* (*)(const uint8_t*, int, int, int, const char*, int, int, double, int, const char*, int, int, const char*);
using DetectAiFn = char* (*)(const uint8_t*, int, int, int, const char*, const char*, const char*);
using AiActionFn = char* (*)(const uint8_t*, int, int, int, const char*, const char*);
using AiStatusFn = char* (*)(const char*);

void write_all_and_close(int fd, const char* data) {
    if (data) {
        size_t len = std::strlen(data);
        size_t off = 0;
        while (off < len) {
            ssize_t n = ::write(fd, data + off, len - off);
            if (n <= 0) break;
            off += static_cast<size_t>(n);
        }
    }
    ::close(fd);
}

std::string read_fd_blocking(int fd) {
    std::string out;
    char buf[4096];
    ssize_t n;
    while ((n = ::read(fd, buf, sizeof(buf))) > 0) {
        out.append(buf, static_cast<size_t>(n));
    }
    ::close(fd);
    return out;
}

}  // namespace

void VisionJob::cancel() {
    if (read_fd >= 0) {
        ::close(read_fd);
        read_fd = -1;
    }
    if (pid > 0) {
        ::kill(pid, SIGKILL);
        int st = 0;
        ::waitpid(pid, &st, 0);
        pid = -1;
    }
    buffer.clear();
}

bool VisionJob::poll_read_done() {
    if (read_fd < 0) return false;
    char buf[8192];
    while (true) {
        ssize_t n = ::read(read_fd, buf, sizeof(buf));
        if (n > 0) {
            buffer.append(buf, static_cast<size_t>(n));
            continue;
        }
        if (n == 0) {
            ::close(read_fd);
            read_fd = -1;
            if (pid > 0) {
                int st = 0;
                ::waitpid(pid, &st, 0);
                pid = -1;
            }
            return true;
        }
        if (errno == EAGAIN || errno == EWOULDBLOCK) return false;
        // Read error
        ::close(read_fd);
        read_fd = -1;
        if (pid > 0) {
            int st = 0;
            ::waitpid(pid, &st, 0);
            pid = -1;
        }
        return true;
    }
}

std::string VisionBridge::resolve_plugin_path(const std::string& self_exe) {
    std::error_code ec;
    fs::path exe = self_exe.empty() ? fs::read_symlink("/proc/self/exe", ec) : fs::path(self_exe);
    if (!exe.empty()) {
        fs::path bin_dir = exe.parent_path();
        for (const auto& c : {
                 bin_dir / "libhss_vision.so",
                 bin_dir.parent_path() / "lib" / "hyprsmartshot" / "libhss_vision.so",
                 bin_dir.parent_path() / "lib64" / "hyprsmartshot" / "libhss_vision.so",
             }) {
            if (fs::is_regular_file(c, ec)) return c.string();
        }
    }
    for (const auto& c : {
             fs::path(HSS_LIBDIR) / "hyprsmartshot" / "libhss_vision.so",
             fs::path("/usr/lib/hyprsmartshot/libhss_vision.so"),
             fs::path("/usr/local/lib/hyprsmartshot/libhss_vision.so"),
         }) {
        if (fs::is_regular_file(c, ec)) return c.string();
    }
    return "libhss_vision.so";
}

VisionJob VisionBridge::spawn_cv_job(const PixelBuffer& freeze_img,
                                     const MonitorInfo& monitor,
                                     const std::string& preset_key,
                                     const nlohmann::json& cfg,
                                     const std::string& self_exe) {
    VisionJob job;
    int pfd[2];
    if (::pipe2(pfd, O_CLOEXEC) < 0) return job;

    std::string plugin_path = resolve_plugin_path(self_exe);
    std::string cfg_str = cfg.dump();

    pid_t pid = ::fork();
    if (pid < 0) {
        ::close(pfd[0]);
        ::close(pfd[1]);
        return job;
    }
    if (pid == 0) {
        ::close(pfd[0]);
        void* handle = ::dlopen(plugin_path.c_str(), RTLD_NOW | RTLD_LOCAL);
        if (!handle) {
            write_all_and_close(pfd[1], R"({"ok":false,"error":"dlopen libhss_vision.so failed","boxes":[]})");
            ::_exit(1);
        }
        auto fn = reinterpret_cast<DetectCvFn>(::dlsym(handle, "hss_vision_detect_cv"));
        auto free_fn = reinterpret_cast<FreeStrFn>(::dlsym(handle, "hss_vision_free_str"));
        if (!fn || !free_fn) {
            write_all_and_close(pfd[1], R"({"ok":false,"error":"missing symbol","boxes":[]})");
            ::_exit(1);
        }
        char* out = fn(freeze_img.data.data(), freeze_img.width, freeze_img.height, freeze_img.stride,
                       cfg_str.c_str(), monitor.x, monitor.y, monitor.scale,
                       monitor.active_workspace_id, monitor.name.c_str(),
                       monitor.logical_width(), monitor.logical_height(), preset_key.c_str());
        write_all_and_close(pfd[1], out);
        free_fn(out);
        ::_exit(0);
    }

    ::close(pfd[1]);
    int flags = ::fcntl(pfd[0], F_GETFL, 0);
    ::fcntl(pfd[0], F_SETFL, flags | O_NONBLOCK);
    job.pid = pid;
    job.read_fd = pfd[0];
    return job;
}

VisionJob VisionBridge::spawn_ai_boxes_job(const PixelBuffer& freeze_img,
                                           const std::vector<DetectedBox>& cv_boxes,
                                           const nlohmann::json& cfg,
                                           const std::string& self_exe) {
    VisionJob job;
    int pfd[2];
    if (::pipe2(pfd, O_CLOEXEC) < 0) return job;

    std::string plugin_path = resolve_plugin_path(self_exe);
    std::string cfg_str = cfg.dump();
    nlohmann::json cv_arr = nlohmann::json::array();
    for (const auto& b : cv_boxes) {
        cv_arr.push_back({{"x", b.x}, {"y", b.y}, {"w", b.w}, {"h", b.h}});
    }
    std::string cv_str = cv_arr.dump();

    pid_t pid = ::fork();
    if (pid < 0) {
        ::close(pfd[0]);
        ::close(pfd[1]);
        return job;
    }
    if (pid == 0) {
        ::close(pfd[0]);
        void* handle = ::dlopen(plugin_path.c_str(), RTLD_NOW | RTLD_LOCAL);
        if (!handle) {
            write_all_and_close(pfd[1], R"({"ok":false,"error":"dlopen libhss_vision.so failed","boxes":[]})");
            ::_exit(1);
        }
        auto fn = reinterpret_cast<DetectAiFn>(::dlsym(handle, "hss_vision_detect_ai"));
        auto free_fn = reinterpret_cast<FreeStrFn>(::dlsym(handle, "hss_vision_free_str"));
        if (!fn || !free_fn) {
            write_all_and_close(pfd[1], R"({"ok":false,"error":"missing symbol","boxes":[]})");
            ::_exit(1);
        }
        char* out = fn(freeze_img.data.data(), freeze_img.width, freeze_img.height, freeze_img.stride,
                       cfg_str.c_str(), cv_str.c_str(), "");
        write_all_and_close(pfd[1], out);
        free_fn(out);
        ::_exit(0);
    }

    ::close(pfd[1]);
    int flags = ::fcntl(pfd[0], F_GETFL, 0);
    ::fcntl(pfd[0], F_SETFL, flags | O_NONBLOCK);
    job.pid = pid;
    job.read_fd = pfd[0];
    return job;
}

VisionAiActionOut VisionBridge::run_ai_action_forked(const PixelBuffer& cropped,
                                                     const std::string& action_mode,
                                                     const nlohmann::json& cfg,
                                                     const std::string& self_exe) {
    VisionAiActionOut res;
    int pfd[2];
    if (::pipe2(pfd, O_CLOEXEC) < 0) {
        res.error = "pipe failed";
        return res;
    }
    std::string plugin_path = resolve_plugin_path(self_exe);
    std::string cfg_str = cfg.dump();

    pid_t pid = ::fork();
    if (pid < 0) {
        ::close(pfd[0]);
        ::close(pfd[1]);
        res.error = "fork failed";
        return res;
    }
    if (pid == 0) {
        ::close(pfd[0]);
        void* handle = ::dlopen(plugin_path.c_str(), RTLD_NOW | RTLD_LOCAL);
        if (!handle) {
            write_all_and_close(pfd[1], R"({"ok":false,"text":"","error":"dlopen libhss_vision.so failed"})");
            ::_exit(1);
        }
        auto fn = reinterpret_cast<AiActionFn>(::dlsym(handle, "hss_vision_run_ai_action"));
        auto free_fn = reinterpret_cast<FreeStrFn>(::dlsym(handle, "hss_vision_free_str"));
        char* out = (fn && free_fn)
                        ? fn(cropped.data.data(), cropped.width, cropped.height, cropped.stride,
                             action_mode.c_str(), cfg_str.c_str())
                        : nullptr;
        write_all_and_close(pfd[1], out ? out : R"({"ok":false,"text":"","error":"missing symbol"})");
        if (out && free_fn) free_fn(out);
        ::_exit(0);
    }

    ::close(pfd[1]);
    std::string raw = read_fd_blocking(pfd[0]);
    int st = 0;
    ::waitpid(pid, &st, 0);
    try {
        auto j = nlohmann::json::parse(raw);
        res.ok = j.value("ok", false);
        res.text = j.value("text", std::string());
        res.error = j.value("error", std::string());
    } catch (const std::exception& e) {
        res.error = e.what();
    }
    return res;
}

VisionAiStatus VisionBridge::check_ai_status_forked(const nlohmann::json& cfg,
                                                    const std::string& self_exe) {
    VisionAiStatus st_out;
    int pfd[2];
    if (::pipe2(pfd, O_CLOEXEC) < 0) return st_out;
    std::string plugin_path = resolve_plugin_path(self_exe);
    std::string cfg_str = cfg.dump();

    pid_t pid = ::fork();
    if (pid < 0) {
        ::close(pfd[0]);
        ::close(pfd[1]);
        return st_out;
    }
    if (pid == 0) {
        ::close(pfd[0]);
        void* handle = ::dlopen(plugin_path.c_str(), RTLD_NOW | RTLD_LOCAL);
        if (!handle) {
            write_all_and_close(pfd[1], R"({"enabled":false,"reachable":false,"detail":"libhss_vision.so not found"})");
            ::_exit(1);
        }
        auto fn = reinterpret_cast<AiStatusFn>(::dlsym(handle, "hss_vision_check_ai_status"));
        auto free_fn = reinterpret_cast<FreeStrFn>(::dlsym(handle, "hss_vision_free_str"));
        char* out = (fn && free_fn) ? fn(cfg_str.c_str()) : nullptr;
        write_all_and_close(pfd[1], out ? out : "{}");
        if (out && free_fn) free_fn(out);
        ::_exit(0);
    }

    ::close(pfd[1]);
    std::string raw = read_fd_blocking(pfd[0]);
    int st = 0;
    ::waitpid(pid, &st, 0);
    try {
        auto j = nlohmann::json::parse(raw);
        st_out.enabled = j.value("enabled", false);
        st_out.reachable = j.value("reachable", false);
        st_out.provider = j.value("provider", std::string());
        st_out.model = j.value("model", std::string());
        st_out.trigger = j.value("trigger", std::string());
        st_out.detail = j.value("detail", std::string());
    } catch (...) {
    }
    return st_out;
}

std::vector<DetectedBox> VisionBridge::parse_boxes_json(const std::string& raw_json,
                                                        std::string* error_out,
                                                        double* elapsed_ms_out) {
    std::vector<DetectedBox> out;
    if (raw_json.empty()) return out;
    try {
        auto j = nlohmann::json::parse(raw_json);
        if (error_out && !j.value("ok", true)) {
            *error_out = j.value("error", std::string("unknown error"));
        }
        if (elapsed_ms_out && j.contains("elapsed_ms") && j["elapsed_ms"].is_number()) {
            *elapsed_ms_out = j["elapsed_ms"].get<double>();
        }
        if (j.contains("boxes") && j["boxes"].is_array()) {
            out.reserve(j["boxes"].size());
            for (const auto& item : j["boxes"]) {
                if (!item.is_object()) continue;
                DetectedBox b;
                b.id = item.value("id", 0);
                b.x = item.value("x", 0);
                b.y = item.value("y", 0);
                b.w = item.value("w", 0);
                b.h = item.value("h", 0);
                b.area = item.value("area", b.w * b.h);
                b.extent = item.value("extent", 1.0);
                b.contrast = item.value("contrast", 30.0);
                b.type = item.value("type", std::string("detected"));
                b.label = item.value("label", std::string());
                b.title = item.value("title", std::string());
                b.wm_class = item.value("class", std::string());
                b.source = item.value("source", std::string("cv"));
                b.rating_source = item.value("rating_source", std::string("heuristic"));
                b.is_client = item.value("is_client", false);
                b.floating = item.value("floating", false);
                b.pinned = item.value("pinned", false);
                b.is_layer = item.value("is_layer", false);
                b.focus_history_id = item.value("focusHistoryID", 999);
                b.confidence = item.value("confidence", 0.80);
                b.score = item.value("score", 80);
                b.depth = item.value("depth", 0);
                out.push_back(std::move(b));
            }
        }
    } catch (const std::exception& e) {
        if (error_out) *error_out = e.what();
    }
    return out;
}

}  // namespace hss
