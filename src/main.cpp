#include "core/actions.hpp"
#include "core/config.hpp"
#include "core/hyprland_ipc.hpp"
#include "core/i18n.hpp"
#include "ipc/daemon.hpp"
#include "overlay/overlay.hpp"
#include "vision/vision_bridge.hpp"
#include "wayland/pin_window.hpp"

#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <string>
#include <vector>

namespace {

void show_help() {
    std::cout
        << "HyprSmartShot v" << HSS_VERSION << "\n"
        << "Standalone C++23 Wayland screenshot & CV utility crafted for Hyprland.\n\n"
        << "Usage:\n"
        << "  hyprsmartshot [COMMAND] [OPTIONS]\n\n"
        << "Commands:\n"
        << "  universal       Smart UI detection and interactive overlay (default)\n"
        << "  screen          Fullscreen interactive overlay\n"
        << "  full            Instant fullscreen capture without opening overlay\n"
        << "  pin             Display image in a pinned, floating native Wayland window\n"
        << "  daemon          Run persistent lightweight background daemon (<10 MB idle RAM)\n"
        << "  settings        Open on-demand GTK4 settings window\n"
        << "  status          Query running daemon status (RSS, uptime, outputs)\n"
        << "  quit            Stop running daemon cleanly\n\n"
        << "Options:\n"
        << "  --mode <name>       Select capture mode (universal, screen, window, full)\n"
        << "  --preset <name>     Override active detection preset (default, browser, terminal, game)\n"
        << "  --config <path>     Use custom config.json path\n"
        << "  --ai                Enable AI box detection pass alongside CV\n"
        << "  --no-ai             Disable AI pass even if ai.trigger=auto\n"
        << "  --no-cv             Skip OpenCV detection pass\n"
        << "  --standalone        Bypass running daemon and execute directly in-process\n"
        << "  --doctor            Run environment, config, Pywal, Wayland, and AI readiness checks\n"
        << "  -h, --help          Display this help message\n"
        << "  -v, --version       Display version information\n";
}

void show_version() {
    std::cout << "hyprsmartshot v" << HSS_VERSION << "\n";
}

int parse_pin_and_run(int argc, char** argv, int start_idx, const nlohmann::json& cfg) {
    hss::PinOptions opts;
    std::vector<std::string> pos;
    for (int i = start_idx; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "-h" || a == "--help") {
            std::cout << "Usage: hyprsmartshot pin [--border-color HEX] [--bg-color HEX] [--border-width N] [--keep|--delete] <image_path> [x] [y] [width] [height]\n";
            return 0;
        } else if (a == "-v" || a == "--version") {
            std::cout << "hyprsmartshot-pin v" << HSS_VERSION << "\n";
            return 0;
        } else if (a == "--keep") {
            opts.delete_source = false;
        } else if (a == "--delete") {
            opts.delete_source = true;
        } else if (a == "--border-color" && i + 1 < argc) {
            opts.border_color = argv[++i];
        } else if (a == "--bg-color" && i + 1 < argc) {
            opts.bg_color = argv[++i];
        } else if (a == "--border-width" && i + 1 < argc) {
            try { opts.border_width = std::stoi(argv[++i]); } catch (...) {}
        } else if (!a.empty() && a.front() == '-') {
            std::cerr << "Error: Unknown pin option '" << a << "'\n";
            return 1;
        } else {
            pos.push_back(a);
        }
    }

    if (pos.empty()) {
        std::cerr << "Error: Missing image path for 'pin'\n"
                  << "Usage: hyprsmartshot pin <image_path> [x] [y] [width] [height]\n";
        return 1;
    }
    opts.image_path = pos[0];
    try {
        if (pos.size() >= 2) opts.x = std::stoi(pos[1]);
        if (pos.size() >= 3) opts.y = std::stoi(pos[2]);
        if (pos.size() >= 4) opts.width = std::stoi(pos[3]);
        if (pos.size() >= 5) opts.height = std::stoi(pos[4]);
    } catch (...) {}

    return hss::PinWindow::run(opts, cfg);
}

int run_doctor(const std::string& explicit_config, const std::string& self_exe) {
    auto cfg = hss::ConfigManager::load_config(explicit_config);
    auto user_cfg = hss::ConfigManager::resolve_config_path(explicit_config);
    auto drop_dir = hss::ConfigManager::resolve_config_dir(explicit_config) / "config.d";
    auto pal = hss::ConfigManager::resolve_palette(cfg);
    auto ai = hss::VisionBridge::check_ai_status_forked(cfg, self_exe);

    std::cout << "HyprSmartShot Doctor (v" << HSS_VERSION << " native C++23)\n"
              << "Binary: " << self_exe << "\n"
              << "DataDir: " << hss::ConfigManager::resolve_data_dir(self_exe).string() << "\n"
              << "User config: " << user_cfg.string()
              << " (exists=" << (std::filesystem::is_regular_file(user_cfg) ? "true" : "false")
              << ") | drop-ins dir=" << drop_dir.string() << "\n"
              << "Hyprland socket: " << (hss::HyprlandIpc::available() ? "connected" : "not detected") << "\n"
              << "Daemon: " << (hss::Daemon::ping() ? "running" : "stopped (standalone fallback active)") << "\n"
              << "Theme: source=" << pal.source
              << " isLight=" << (pal.is_light ? "true" : "false")
              << " accent=" << pal.accent.to_hex()
              << " bg=" << pal.background.to_hex() << "\n"
              << "Rating: enabled=" << (cfg["rating"].value("enabled", true) ? "true" : "false")
              << " minConf=" << cfg["rating"].value("minConfidence", 0.30)
              << " adaptive=" << (cfg["rating"].value("adaptiveLearning", true) ? "true" : "false") << "\n"
              << "AI: enabled=" << (ai.enabled ? "true" : "false")
              << " provider=" << ai.provider
              << " trigger=" << ai.trigger
              << " reachable=" << (ai.reachable ? "true" : "false")
              << " (" << ai.detail << ")\n";

    std::vector<std::string> opt_tools = {"satty", "tesseract", "wl-copy", "caelestia-toast", "notify-send"};
    std::cout << "Optional helpers:";
    for (const auto& t : opt_tools) {
        std::cout << " " << t << "=" << (hss::Actions::command_exists(t) ? "ok" : "missing");
    }
    std::cout << "\n";
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    std::error_code ec;
    auto self_path = std::filesystem::read_symlink("/proc/self/exe", ec);
    std::string self_exe = ec ? std::string(argv[0]) : self_path.string();

    // Direct symlink invocation: hyprsmartshot-pin <path> ...
    std::string invoked = std::filesystem::path(argv[0]).filename().string();
    if (invoked == "hyprsmartshot-pin") {
        auto cfg = hss::ConfigManager::load_config();
        return parse_pin_and_run(argc, argv, 1, cfg);
    }

    // Dedicated subcommand 'pin'
    if (argc >= 2 && std::string(argv[1]) == "pin") {
        auto cfg = hss::ConfigManager::load_config();
        return parse_pin_and_run(argc, argv, 2, cfg);
    }

    std::string mode;
    std::string cli_preset = std::getenv("SMARTSHOT_PRESET") ? std::getenv("SMARTSHOT_PRESET") : "";
    std::string cli_config = std::getenv("SMARTSHOT_CONFIG") ? std::getenv("SMARTSHOT_CONFIG") : "";
    int ai_force = -1;
    bool no_cv = (std::getenv("SMARTSHOT_NO_CV") && std::string(std::getenv("SMARTSHOT_NO_CV")) == "1");
    bool doctor_mode = false;
    bool force_standalone = false;
    bool benchmark_exit = false;
    std::vector<std::string> positional;

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "-h" || arg == "--help" || arg == "help") {
            show_help();
            return 0;
        } else if (arg == "-v" || arg == "--version" || arg == "version") {
            show_version();
            return 0;
        } else if (arg == "--doctor") {
            doctor_mode = true;
        } else if (arg == "--ai") {
            ai_force = 1;
        } else if (arg == "--no-ai") {
            ai_force = 0;
        } else if (arg == "--no-cv") {
            no_cv = true;
        } else if (arg == "--standalone") {
            force_standalone = true;
        } else if (arg == "--benchmark-exit") {
            benchmark_exit = true;
        } else if (arg.rfind("--preset=", 0) == 0) {
            cli_preset = arg.substr(9);
        } else if (arg == "--preset") {
            if (i + 1 >= argc) { std::cerr << "Error: Missing value for --preset\n"; return 1; }
            cli_preset = argv[++i];
        } else if (arg.rfind("--mode=", 0) == 0) {
            mode = arg.substr(7);
        } else if (arg == "--mode") {
            if (i + 1 >= argc) { std::cerr << "Error: Missing value for --mode\n"; return 1; }
            mode = argv[++i];
        } else if (arg.rfind("--config=", 0) == 0) {
            cli_config = arg.substr(9);
        } else if (arg == "--config") {
            if (i + 1 >= argc) { std::cerr << "Error: Missing value for --config\n"; return 1; }
            cli_config = argv[++i];
        } else if (!arg.empty() && arg.front() == '-') {
            std::cerr << "Error: Unknown option '" << arg << "'\n"
                      << "Run 'hyprsmartshot --help' for usage.\n";
            return 1;
        } else {
            positional.push_back(arg);
        }
    }

    if (positional.size() > 1) {
        std::cerr << "Error: Unexpected argument '" << positional[1] << "'\n"
                  << "Run 'hyprsmartshot --help' for usage.\n";
        return 1;
    }

    if (mode.empty()) {
        mode = positional.empty() ? "universal" : positional[0];
    } else if (!positional.empty()) {
        std::cerr << "Error: Unexpected argument '" << positional[0] << "'\n"
                  << "Run 'hyprsmartshot --help' for usage.\n";
        return 1;
    }

    if (doctor_mode) {
        return run_doctor(cli_config, self_exe);
    }

    if (mode == "daemon") {
        return hss::Daemon::run_server(cli_config, self_exe);
    }

    if (mode == "settings") {
        hss::Actions::launch_settings_gui(self_exe);
        return 0;
    }

    if (mode == "status") {
        auto res = hss::Daemon::send_command({{"cmd", "status"}}, 1000);
        if (!res) {
            std::cout << "{\"running\":false}\n";
            return 1;
        }
        std::cout << res->dump(2) << "\n";
        return 0;
    }

    if (mode == "quit") {
        auto res = hss::Daemon::send_command({{"cmd", "quit"}}, 1000);
        return (res && res->value("ok", false)) ? 0 : 1;
    }

    if (mode != "universal" && mode != "screen" && mode != "window" && mode != "full") {
        std::cerr << "Error: Unknown command '" << mode << "'\n"
                  << "Valid commands: universal, screen, full, pin, daemon, settings, status, quit\n"
                  << "Run 'hyprsmartshot --help' for usage.\n";
        return 1;
    }

    // Hybrid client fast path: forward to running daemon if available (unless --standalone)
    if (!force_standalone) {
        nlohmann::json req_json = {
            {"cmd", "capture"},
            {"mode", mode},
            {"preset", cli_preset},
            {"config", cli_config},
            {"ai_force", ai_force},
            {"no_cv", no_cv},
            {"benchmark_exit", benchmark_exit},
        };
        if (auto res = hss::Daemon::send_command(req_json, 300000)) {
            if (benchmark_exit) {
                std::cout << res->dump() << "\n";
            }
            return res->value("rc", res->value("ok", false) ? 0 : 1);
        }
    }

    // Automatic standalone fallback (0 MB idle RAM)
    auto cfg = hss::ConfigManager::load_config(cli_config);
    if (cfg.contains("theme") && cfg["theme"].is_object() && cfg["theme"].value("syncSatty", false)) {
        hss::ConfigManager::export_satty_pywal_config(cfg);
    }

    std::string lang = std::getenv("SMARTSHOT_LANG") ? std::getenv("SMARTSHOT_LANG") : cfg.value("language", std::string("en"));
    hss::I18n i18n;
    i18n.load(lang, hss::ConfigManager::resolve_config_dir(cli_config), hss::ConfigManager::resolve_data_dir(self_exe));

    hss::CaptureRequest req;
    req.mode = mode;
    req.preset = cli_preset;
    req.explicit_config = cli_config;
    req.ai_force = ai_force;
    req.no_cv = no_cv;
    req.benchmark_exit = benchmark_exit;

    return hss::OverlaySession::run(req, cfg, i18n, self_exe, nullptr, nullptr);
}
