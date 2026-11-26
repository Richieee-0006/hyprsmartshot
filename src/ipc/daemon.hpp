#pragma once

#include "overlay/overlay.hpp"

#include <optional>
#include <string>

#include <nlohmann/json.hpp>

namespace hss {

class Daemon {
public:
    static std::string socket_path();
    static long read_self_rss_kb();

    // Run persistent lightweight daemon (idle <10 MB RSS, 0 GPU/surfaces when idle)
    static int run_server(const std::string& explicit_config, const std::string& self_exe);

    // Thin client helpers — return std::nullopt if daemon is not reachable
    static std::optional<nlohmann::json> send_command(const nlohmann::json& payload,
                                                      int timeout_ms = 60000);
    static bool ping();
    static bool notify_reload_config();
};

}  // namespace hss
