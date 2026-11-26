#pragma once

#include <optional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace hss {

struct MonitorInfo {
    std::string name;
    int x = 0;
    int y = 0;
    int width = 1920;   // physical pixels reported by Hyprland
    int height = 1080;
    double scale = 1.0;
    int transform = 0;
    int active_workspace_id = 0;
    bool focused = false;

    int logical_width() const;
    int logical_height() const;
};

struct ClientWindow {
    int x = 0;
    int y = 0;
    int w = 0;
    int h = 0;
    bool floating = false;
    bool pinned = false;
    bool mapped = true;
    bool hidden = false;
    bool is_layer = false;
    int workspace_id = 0;
    std::string workspace_name;
    int focus_history_id = 999;
    std::string wm_class;
    std::string title;
};

class HyprlandIpc {
public:
    static std::string socket_path();
    static bool available();
    static std::optional<std::string> request(const std::string& command, int timeout_ms = 1000);

    static std::vector<MonitorInfo> get_monitors();
    static MonitorInfo get_focused_monitor();
    static std::vector<ClientWindow> get_clients_and_layers(const MonitorInfo& monitor);
    static std::string get_active_window_class();
    static bool dispatch(const std::string& args);

    // Pure helpers exposed for unit tests
    static std::vector<ClientWindow> parse_clients_and_layers_json(
        const nlohmann::json& clients_json,
        const nlohmann::json& layers_json,
        const std::string& monitor_name,
        int monitor_w,
        int monitor_h);
};

}  // namespace hss
