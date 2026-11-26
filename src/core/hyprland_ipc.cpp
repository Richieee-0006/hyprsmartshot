#include "core/hyprland_ipc.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <poll.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

namespace hss {

int MonitorInfo::logical_width() const {
    bool rotated = (transform == 1 || transform == 3 || transform == 5 || transform == 7);
    int phys = rotated ? height : width;
    return std::max(1, static_cast<int>(std::lround(phys / (scale > 0.0 ? scale : 1.0))));
}

int MonitorInfo::logical_height() const {
    bool rotated = (transform == 1 || transform == 3 || transform == 5 || transform == 7);
    int phys = rotated ? width : height;
    return std::max(1, static_cast<int>(std::lround(phys / (scale > 0.0 ? scale : 1.0))));
}

std::string HyprlandIpc::socket_path() {
    const char* his = std::getenv("HYPRLAND_INSTANCE_SIGNATURE");
    if (!his || !*his) return "";
    const char* xdg = std::getenv("XDG_RUNTIME_DIR");
    std::string base = (xdg && *xdg) ? std::string(xdg) : "/tmp";
    std::string p1 = base + "/hypr/" + his + "/.socket.sock";
    std::error_code ec;
    if (std::filesystem::exists(p1, ec)) return p1;
    std::string p2 = std::string("/tmp/hypr/") + his + "/.socket.sock";
    if (std::filesystem::exists(p2, ec)) return p2;
    return p1;
}

bool HyprlandIpc::available() {
    std::string p = socket_path();
    std::error_code ec;
    return !p.empty() && std::filesystem::exists(p, ec);
}

std::optional<std::string> HyprlandIpc::request(const std::string& command, int timeout_ms) {
    std::string path = socket_path();
    if (path.empty() || path.size() >= sizeof(sockaddr_un::sun_path)) {
        return std::nullopt;
    }

    int fd = ::socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (fd < 0) return std::nullopt;

    struct FdGuard {
        int fd;
        ~FdGuard() { if (fd >= 0) ::close(fd); }
    } guard{fd};

    sockaddr_un addr{};
    addr.sun_family = AF_UNIX;
    std::strncpy(addr.sun_path, path.c_str(), sizeof(addr.sun_path) - 1);

    if (::connect(fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
        return std::nullopt;
    }

    size_t sent = 0;
    while (sent < command.size()) {
        ssize_t n = ::send(fd, command.data() + sent, command.size() - sent, MSG_NOSIGNAL);
        if (n <= 0) return std::nullopt;
        sent += static_cast<size_t>(n);
    }

    std::string response;
    response.reserve(8192);
    char buf[8192];

    while (true) {
        pollfd pfd{};
        pfd.fd = fd;
        pfd.events = POLLIN;
        int pr = ::poll(&pfd, 1, timeout_ms);
        if (pr <= 0) break;
        ssize_t n = ::recv(fd, buf, sizeof(buf), 0);
        if (n <= 0) break;
        response.append(buf, static_cast<size_t>(n));
    }
    return response;
}

std::vector<MonitorInfo> HyprlandIpc::get_monitors() {
    std::vector<MonitorInfo> out;
    auto raw = request("j/monitors");
    if (!raw || raw->empty()) return out;
    try {
        auto j = nlohmann::json::parse(*raw);
        if (!j.is_array()) return out;
        for (const auto& m : j) {
            if (!m.is_object()) continue;
            MonitorInfo info;
            info.name = m.value("name", std::string());
            info.x = m.value("x", 0);
            info.y = m.value("y", 0);
            info.width = m.value("width", 1920);
            info.height = m.value("height", 1080);
            info.scale = m.value("scale", 1.0);
            if (info.scale <= 0.0) info.scale = 1.0;
            info.transform = m.value("transform", 0);
            info.focused = m.value("focused", false);
            if (m.contains("activeWorkspace") && m["activeWorkspace"].is_object()) {
                info.active_workspace_id = m["activeWorkspace"].value("id", 0);
            }
            out.push_back(std::move(info));
        }
    } catch (...) {
    }
    return out;
}

MonitorInfo HyprlandIpc::get_focused_monitor() {
    auto mons = get_monitors();
    for (const auto& m : mons) {
        if (m.focused) return m;
    }
    if (!mons.empty()) return mons.front();
    return MonitorInfo{};
}

std::vector<ClientWindow> HyprlandIpc::parse_clients_and_layers_json(
    const nlohmann::json& clients_json,
    const nlohmann::json& layers_json,
    const std::string& monitor_name,
    int monitor_w,
    int monitor_h) {
    std::vector<ClientWindow> result;

    if (clients_json.is_array()) {
        for (const auto& c : clients_json) {
            if (!c.is_object()) continue;
            ClientWindow w;
            if (c.contains("at") && c["at"].is_array() && c["at"].size() == 2) {
                w.x = c["at"][0].get<int>();
                w.y = c["at"][1].get<int>();
            }
            if (c.contains("size") && c["size"].is_array() && c["size"].size() == 2) {
                w.w = c["size"][0].get<int>();
                w.h = c["size"][1].get<int>();
            }
            w.floating = c.value("floating", false);
            w.pinned = c.value("pinned", false);
            w.mapped = c.value("mapped", true);
            w.hidden = c.value("hidden", false);
            w.is_layer = c.value("is_layer", false);
            w.focus_history_id = c.value("focusHistoryID", 999);
            w.wm_class = c.value("class", std::string());
            w.title = c.value("title", std::string());
            if (c.contains("workspace")) {
                if (c["workspace"].is_object()) {
                    w.workspace_id = c["workspace"].value("id", 0);
                    w.workspace_name = c["workspace"].value("name", std::string());
                } else if (c["workspace"].is_number_integer()) {
                    w.workspace_id = c["workspace"].get<int>();
                }
            }
            result.push_back(std::move(w));
        }
    }

    if (layers_json.is_object()) {
        auto process_mon = [&](const nlohmann::json& mon_obj) {
            if (!mon_obj.is_object() || !mon_obj.contains("levels") || !mon_obj["levels"].is_object()) {
                return;
            }
            for (const char* lvl : {"1", "2", "3"}) {
                if (!mon_obj["levels"].contains(lvl) || !mon_obj["levels"][lvl].is_array()) continue;
                for (const auto& ls : mon_obj["levels"][lvl]) {
                    if (!ls.is_object()) continue;
                    int lw = ls.value("w", 0);
                    int lh = ls.value("h", 0);
                    if (lw < 24 || lh < 24) continue;
                    if (monitor_w > 0 && monitor_h > 0 &&
                        lw >= monitor_w * 0.90 && lh >= monitor_h * 0.90) {
                        continue;
                    }
                    ClientWindow cw;
                    cw.x = ls.value("x", 0);
                    cw.y = ls.value("y", 0);
                    cw.w = lw;
                    cw.h = lh;
                    cw.floating = true;
                    cw.pinned = true;
                    cw.mapped = true;
                    cw.hidden = false;
                    cw.is_layer = true;
                    cw.focus_history_id = -1;
                    cw.wm_class = ls.value("namespace", std::string("layer-popout"));
                    cw.title = cw.wm_class;
                    result.push_back(std::move(cw));
                }
            }
        };

        if (!monitor_name.empty() && layers_json.contains(monitor_name)) {
            process_mon(layers_json[monitor_name]);
        } else {
            for (auto it = layers_json.begin(); it != layers_json.end(); ++it) {
                process_mon(it.value());
            }
        }
    }

    return result;
}

std::vector<ClientWindow> HyprlandIpc::get_clients_and_layers(const MonitorInfo& monitor) {
    nlohmann::json clients_j = nlohmann::json::array();
    nlohmann::json layers_j = nlohmann::json::object();

    if (auto raw = request("j/clients")) {
        try { clients_j = nlohmann::json::parse(*raw); } catch (...) {}
    }
    if (auto raw = request("j/layers")) {
        try { layers_j = nlohmann::json::parse(*raw); } catch (...) {}
    }

    return parse_clients_and_layers_json(
        clients_j, layers_j, monitor.name, monitor.logical_width(), monitor.logical_height());
}

std::string HyprlandIpc::get_active_window_class() {
    auto raw = request("j/activewindow");
    if (!raw || raw->empty()) return "";
    try {
        auto j = nlohmann::json::parse(*raw);
        if (j.is_object()) return j.value("class", std::string());
    } catch (...) {
    }
    return "";
}

bool HyprlandIpc::dispatch(const std::string& args) {
    auto res = request("dispatch " + args);
    return res && res->find("ok") != std::string::npos;
}

}  // namespace hss
