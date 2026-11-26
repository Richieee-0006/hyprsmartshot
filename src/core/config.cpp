#include "core/config.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <unistd.h>

namespace hss {

namespace fs = std::filesystem;

namespace {

constexpr std::array<const char*, 8> kModuleFiles = {
    "theme.json",
    "detection.json",
    "rating.json",
    "ai.json",
    "ui.json",
    "capture.json",
    "presets.json",
    "appRules.json",
};

std::string trim_str(std::string s) {
    auto not_space = [](unsigned char c) { return !std::isspace(c); };
    s.erase(s.begin(), std::find_if(s.begin(), s.end(), not_space));
    s.erase(std::find_if(s.rbegin(), s.rend(), not_space).base(), s.end());
    return s;
}

std::string to_lower_ascii(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return s;
}

std::string get_env_str(const char* name) {
    const char* v = std::getenv(name);
    return v ? std::string(v) : std::string();
}

}  // namespace

Color Color::from_hex(const std::string& hex, double alpha) {
    std::string s = trim_str(hex);
    if (!s.empty() && s.front() == '#') s.erase(s.begin());
    if (s.size() < 6) {
        return {20.0 / 255.0, 20.0 / 255.0, 25.0 / 255.0, alpha};
    }
    try {
        int r = std::stoi(s.substr(0, 2), nullptr, 16);
        int g = std::stoi(s.substr(2, 2), nullptr, 16);
        int b = std::stoi(s.substr(4, 2), nullptr, 16);
        double a = alpha;
        if (s.size() >= 8) {
            int ai = std::stoi(s.substr(6, 2), nullptr, 16);
            a = std::clamp(ai / 255.0, 0.0, 1.0);
        }
        return {r / 255.0, g / 255.0, b / 255.0, a};
    } catch (...) {
        return {20.0 / 255.0, 20.0 / 255.0, 25.0 / 255.0, alpha};
    }
}

std::string Color::to_hex() const {
    auto clamp255 = [](double v) {
        return std::clamp(static_cast<int>(std::lround(v * 255.0)), 0, 255);
    };
    std::ostringstream oss;
    oss << '#' << std::hex << std::setfill('0')
        << std::setw(2) << clamp255(r)
        << std::setw(2) << clamp255(g)
        << std::setw(2) << clamp255(b);
    return oss.str();
}

Color Color::mix(const Color& a, const Color& b, double t, double alpha) {
    t = std::clamp(t, 0.0, 1.0);
    return {
        a.r + (b.r - a.r) * t,
        a.g + (b.g - a.g) * t,
        a.b + (b.b - a.b) * t,
        alpha,
    };
}

nlohmann::json ConfigManager::default_config() {
    return nlohmann::json{
        {"language", "en"},
        {"ocrLanguages", "eng"},
        {"postSaveHook", ""},
        {"postCopyHook", ""},
        {"activePreset", "default"},
        {"presets", {
            {"default",  {{"name", "Default"},  {"offsetX", 0}, {"offsetY", 0}, {"inset", 0}, {"filter", "all"}}},
            {"browser",  {{"name", "Browser"},  {"offsetX", 0}, {"offsetY", 0}, {"inset", 0}, {"filter", "content"}}},
            {"terminal", {{"name", "Terminal"}, {"offsetX", 0}, {"offsetY", 0}, {"inset", 1}, {"filter", "window"}}},
            {"game",     {{"name", "Game"},     {"offsetX", 0}, {"offsetY", 0}, {"inset", 0}, {"filter", "dense"}}},
        }},
        {"appRules", {
            {"firefox", "browser"}, {"librewolf", "browser"}, {"google-chrome", "browser"},
            {"chromium", "browser"}, {"brave-browser", "browser"}, {"vivaldi", "browser"},
            {"floorp", "browser"}, {"zen-browser", "browser"}, {"discord", "browser"},
            {"vesktop", "browser"}, {"webcord", "browser"}, {"equibop", "browser"},
            {"obsidian", "browser"}, {"com.mojang.minecraft", "game"}, {"minecraft", "game"},
            {"steam_app", "game"}, {"gamescope", "game"}, {"lutris", "game"},
            {"prismlauncher", "game"}, {"kitty", "terminal"}, {"alacritty", "terminal"},
            {"foot", "terminal"}, {"ghostty", "terminal"}, {"wezterm", "terminal"},
            {"konsole", "terminal"}, {"gnome-terminal", "terminal"},
        }},
        {"theme", {
            {"mode", "pywal"},
            {"pywalPath", "~/.cache/wal/colors.json"},
            {"liveWatch", true},
            {"syncSatty", false},
            {"syncPinWindow", true},
            {"dimOpacity", 0.65},
            {"borderRadius", 10},
            {"outlineThickness", 2},
            {"pinBorderWidth", 2},
            {"fontFamily", "JetBrainsMono Nerd Font"},
            {"pywalMap", {
                {"accent", "color1"},
                {"accentHover", "color9"},
                {"selectionBorder", "color2"},
                {"snapBorder", "color3"},
                {"aiAccent", "color5"},
                {"pinBorder", "color4"},
                {"danger", "color1"},
                {"barBorder", "color8"},
                {"textSubtle", "color7"},
            }},
            {"overrides", nlohmann::json::object()},
        }},
        {"detection", {
            {"enableText", true},
            {"enablePanels", true},
            {"enableGrids", true},
            {"enableWindowContent", true},
            {"minArea", 64},
            {"maxAreaRatio", 0.98},
            {"tinyContrastMin", 4.5},
            {"adaptiveTextThreshold", true},
            {"filterIconsFromText", true},
            {"multiColumnParagraphs", true},
            {"maxHeaderHeight", 96},
        }},
        {"rating", {
            {"enabled", true},
            {"minConfidence", 0.30},
            {"adaptiveLearning", true},
            {"learningRate", 0.08},
            {"profilePath", ""},
            {"weights", {
                {"contrast", 0.24},
                {"geometry", 0.18},
                {"edge", 0.22},
                {"interior", 0.14},
                {"semantic", 0.12},
                {"presetFit", 0.10},
            }},
        }},
        {"ai", {
            {"enabled", false},
            {"trigger", "manual"},
            {"provider", "openai_compatible"},
            {"timeoutMs", 35000},
            {"maxImageDim", 960},
            {"defaultAction", "ocr"},
            {"prompt",
             "Locate 5 to 12 distinct visual UI regions in this screenshot (windows, panels, sidebars, code/text blocks, terminal output, top bar, dialogs, buttons, inputs). "
             "You MUST return at least 4 bounding boxes. "
             "Coordinates are normalized 0..1000 where x1,x2 are horizontal (left=0, right=1000) and y1,y2 are vertical (top=0, bottom=1000). "
             "Output ONLY a JSON array: [{\"label\":\"...\",\"type\":\"panel|button|input|slot|text_block\",\"x1\":10,\"y1\":20,\"x2\":500,\"y2\":400,\"confidence\":0.9}]"},
            {"providers", {
                {"copilot", {{"baseUrl", "http://127.0.0.1:4141/v1"}, {"model", "gpt-4.1"}, {"apiKeyEnv", "GITHUB_TOKEN"}, {"apiKey", ""}}},
                {"local_llm", {{"baseUrl", "http://127.0.0.1:8080/v1"}, {"model", "qwen3.6-35b-vision"}, {"apiKeyEnv", "OPENAI_API_KEY"}, {"apiKey", ""}}},
                {"ollama", {{"baseUrl", "http://127.0.0.1:11434/v1"}, {"model", "qwen2.5vl:7b"}, {"apiKeyEnv", ""}, {"apiKey", ""}}},
                {"ovhcloud", {{"baseUrl", "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1"}, {"model", "Qwen2.5-VL-72B-Instruct"}, {"apiKeyEnv", "OVH_API_KEY"}, {"apiKey", ""}}},
                {"kilo", {{"baseUrl", "https://api.kilo.ai/api/gateway"}, {"model", "nvidia/nemotron-3.5-super-vl:free"}, {"apiKeyEnv", "KILO_API_KEY"}, {"apiKey", ""}}},
                {"gemini", {{"baseUrl", "https://generativelanguage.googleapis.com/v1beta"}, {"model", "gemini-3.5-flash-lite"}, {"apiKeyEnv", "GEMINI_API_KEY"}, {"apiKey", ""}}},
                {"openrouter", {{"baseUrl", "https://openrouter.ai/api/v1"}, {"model", "dots-studio/dots-3-note-preview:free"}, {"apiKeyEnv", "OPENROUTER_API_KEY"}, {"apiKey", ""}}},
                {"groq", {{"baseUrl", "https://api.groq.com/openai/v1"}, {"model", "qwen/qwen3.8-27b"}, {"apiKeyEnv", "GROQ_API_KEY"}, {"apiKey", ""}}},
                {"mistral", {{"baseUrl", "https://api.mistral.ai/v1"}, {"model", "mistral-medium-3-5"}, {"apiKeyEnv", "MISTRAL_API_KEY"}, {"apiKey", ""}}},
                {"openai_compatible", {{"baseUrl", "http://127.0.0.1:8080/v1"}, {"model", "qwen3.6-35b-vision"}, {"apiKeyEnv", "OPENAI_API_KEY"}, {"apiKey", ""}}},
            }},
        }},
        {"ui", {
            {"showConfidenceBadge", true},
            {"sortByRating", true},
            {"showMagnifierByDefault", false},
            {"magnifierZoom", 3.0},
            {"magnifierSize", 180},
            {"showHints", true},
            {"animations", true},
        }},
        {"capture", {
            {"imageFormat", "png"},
            {"pngCompression", 4},
            {"defaultSaveDir", ""},
            {"copyAfterSave", true},
        }},
    };
}

nlohmann::json ConfigManager::deep_merge(const nlohmann::json& base, const nlohmann::json& patch) {
    nlohmann::json out = base.is_object() ? base : nlohmann::json::object();
    if (!patch.is_object()) return out;
    for (auto it = patch.begin(); it != patch.end(); ++it) {
        if (it.value().is_object() && out.contains(it.key()) && out[it.key()].is_object()) {
            out[it.key()] = deep_merge(out[it.key()], it.value());
        } else {
            out[it.key()] = it.value();
        }
    }
    return out;
}

std::string ConfigManager::expand_home(const std::string& path) {
    if (path.empty()) return path;
    if (path == "~" || path.rfind("~/", 0) == 0) {
        std::string home = get_env_str("HOME");
        if (!home.empty()) {
            return home + path.substr(1);
        }
    }
    return path;
}

fs::path ConfigManager::resolve_data_dir(const std::string& exe_path) {
    std::string env_dir = get_env_str("SMARTSHOT_DIR");
    if (!env_dir.empty() && fs::is_directory(env_dir)) {
        return fs::path(env_dir);
    }

    std::error_code ec;
    fs::path self = exe_path.empty() ? fs::read_symlink("/proc/self/exe", ec) : fs::path(exe_path);
    if (!self.empty()) {
        fs::path bin_dir = self.parent_path();
        // Dev build dir (<repo>/build/hyprsmartshot) or <repo>/bin/hyprsmartshot
        for (const auto& candidate : {bin_dir.parent_path(), bin_dir.parent_path() / "share" / "hyprsmartshot"}) {
            if (fs::is_directory(candidate / "localization")) {
                return candidate;
            }
        }
    }

    for (const auto& candidate : {
             fs::path(HSS_DATADIR),
             fs::path(expand_home("~/.local/share/hyprsmartshot")),
             fs::path("/usr/share/hyprsmartshot"),
         }) {
        if (fs::is_directory(candidate / "localization")) {
            return candidate;
        }
    }
    return fs::path(HSS_DATADIR);
}

fs::path ConfigManager::resolve_config_dir(const std::string& explicit_config) {
    std::string raw = trim_str(explicit_config.empty() ? get_env_str("SMARTSHOT_CONFIG") : explicit_config);
    if (!raw.empty()) {
        fs::path p(expand_home(raw));
        if (p.has_parent_path()) return p.parent_path();
    }
    std::string xdg = trim_str(get_env_str("XDG_CONFIG_HOME"));
    fs::path base = xdg.empty() ? fs::path(expand_home("~/.config")) : fs::path(expand_home(xdg));
    return base / "hyprsmartshot";
}

fs::path ConfigManager::resolve_config_path(const std::string& explicit_config) {
    std::string raw = trim_str(explicit_config.empty() ? get_env_str("SMARTSHOT_CONFIG") : explicit_config);
    if (!raw.empty()) {
        return fs::path(expand_home(raw));
    }
    return resolve_config_dir() / "config.json";
}

fs::path ConfigManager::resolve_state_dir() {
    std::string xdg = trim_str(get_env_str("XDG_STATE_HOME"));
    fs::path base = xdg.empty() ? fs::path(expand_home("~/.local/state")) : fs::path(expand_home(xdg));
    return base / "hyprsmartshot";
}

fs::path ConfigManager::resolve_cache_dir() {
    std::string xdg = trim_str(get_env_str("XDG_CACHE_HOME"));
    fs::path base = xdg.empty() ? fs::path(expand_home("~/.cache")) : fs::path(expand_home(xdg));
    return base / "hyprsmartshot";
}

fs::path ConfigManager::resolve_save_dir(const nlohmann::json& cfg) {
    if (cfg.contains("capture") && cfg["capture"].is_object()) {
        std::string custom = trim_str(cfg["capture"].value("defaultSaveDir", std::string()));
        if (!custom.empty()) return fs::path(expand_home(custom));
    }
    std::string pics = trim_str(get_env_str("XDG_PICTURES_DIR"));
    fs::path base = pics.empty() ? fs::path(expand_home("~/Pictures")) : fs::path(expand_home(pics));
    return base / "Screenshots";
}

std::optional<nlohmann::json> ConfigManager::read_json_file(const fs::path& p) {
    std::error_code ec;
    if (!fs::is_regular_file(p, ec)) return std::nullopt;
    std::ifstream f(p);
    if (!f) return std::nullopt;
    try {
        nlohmann::json j = nlohmann::json::parse(f);
        if (j.is_object()) return j;
    } catch (...) {
    }
    return std::nullopt;
}

void ConfigManager::apply_module_files_and_dropins(nlohmann::json& cfg, const fs::path& dir) {
    std::error_code ec;
    if (!fs::is_directory(dir, ec)) return;

    for (const char* mod_name : kModuleFiles) {
        auto mod_json = read_json_file(dir / mod_name);
        if (!mod_json) continue;
        std::string key = fs::path(mod_name).stem().string();
        if (mod_json->contains(key) && (*mod_json)[key].is_object()) {
            cfg = deep_merge(cfg, *mod_json);
        } else {
            cfg = deep_merge(cfg, nlohmann::json{{key, *mod_json}});
        }
    }

    fs::path drop_dir = dir / "config.d";
    if (!fs::is_directory(drop_dir, ec)) return;

    std::vector<fs::path> drop_files;
    for (const auto& entry : fs::directory_iterator(drop_dir, ec)) {
        if (entry.is_regular_file(ec) && entry.path().extension() == ".json") {
            drop_files.push_back(entry.path());
        }
    }
    std::sort(drop_files.begin(), drop_files.end());
    for (const auto& f : drop_files) {
        if (auto drop_json = read_json_file(f)) {
            cfg = deep_merge(cfg, *drop_json);
        }
    }
}

nlohmann::json ConfigManager::load_config(const std::string& explicit_config,
                                          const nlohmann::json& cli_overrides) {
    nlohmann::json cfg = default_config();

    fs::path data_dir = resolve_data_dir();
    fs::path bundled_dir = data_dir / "config" / "hyprsmartshot";
    if (auto bundled = read_json_file(bundled_dir / "config.json")) {
        cfg = deep_merge(cfg, *bundled);
    }
    apply_module_files_and_dropins(cfg, bundled_dir);

    fs::path user_path = resolve_config_path(explicit_config);
    fs::path user_dir = user_path.parent_path();
    if (auto user_json = read_json_file(user_path)) {
        cfg = deep_merge(cfg, *user_json);
    }
    apply_module_files_and_dropins(cfg, user_dir);

    if (cli_overrides.is_object() && !cli_overrides.empty()) {
        cfg = deep_merge(cfg, cli_overrides);
    }
    return cfg;
}

fs::path ConfigManager::save_user_config(const nlohmann::json& data,
                                         const std::string& explicit_config) {
    fs::path target = resolve_config_path(explicit_config);
    std::error_code ec;
    fs::create_directories(target.parent_path(), ec);
    fs::path tmp = target;
    tmp += ".tmp." + std::to_string(getpid());
    {
        std::ofstream f(tmp, std::ios::binary | std::ios::trunc);
        if (!f) throw std::runtime_error("Failed to open config temp file: " + tmp.string());
        f << data.dump(2) << '\n';
        f.flush();
        if (!f) throw std::runtime_error("Failed to write config temp file: " + tmp.string());
    }
    fs::rename(tmp, target);
    return target;
}

fs::path ConfigManager::patch_user_config(const nlohmann::json& patch,
                                          const std::string& explicit_config) {
    fs::path target = resolve_config_path(explicit_config);
    nlohmann::json existing = read_json_file(target).value_or(nlohmann::json::object());
    nlohmann::json merged = deep_merge(existing, patch);
    return save_user_config(merged, explicit_config);
}

ThemePalette ConfigManager::resolve_palette(const nlohmann::json& cfg) {
    ThemePalette pal;
    const nlohmann::json theme = (cfg.contains("theme") && cfg["theme"].is_object())
                                     ? cfg["theme"]
                                     : nlohmann::json::object();

    pal.dim_opacity = std::clamp(theme.value("dimOpacity", 0.65), 0.0, 0.95);
    pal.border_radius = std::clamp(theme.value("borderRadius", 10.0), 0.0, 24.0);
    pal.outline_thickness = std::clamp(theme.value("outlineThickness", 2.0), 1.0, 8.0);
    pal.pin_border_width = std::clamp(theme.value("pinBorderWidth", 2.0), 0.0, 8.0);
    std::string font = trim_str(theme.value("fontFamily", std::string("JetBrainsMono Nerd Font")));
    if (!font.empty()) pal.font_family = font;

    std::string mode = to_lower_ascii(theme.value("mode", std::string("pywal")));
    std::string pywal_path = expand_home(theme.value("pywalPath", std::string("~/.cache/wal/colors.json")));

    std::optional<nlohmann::json> wal;
    if (mode == "pywal" || mode == "auto") {
        wal = read_json_file(pywal_path);
    }

    if (wal && wal->contains("colors") && (*wal)["colors"].is_object()) {
        const auto& colors = (*wal)["colors"];
        const auto special = (wal->contains("special") && (*wal)["special"].is_object())
                                 ? (*wal)["special"]
                                 : nlohmann::json::object();

        std::string bg_hex = special.value("background", colors.value("color0", std::string("#141419")));
        std::string fg_hex = special.value("foreground", colors.value("color15", std::string("#ffffff")));
        Color bg = Color::from_hex(bg_hex, 0.90);
        Color fg = Color::from_hex(fg_hex, 1.0);

        pal.source = "pywal";
        pal.is_light = bg.luminance() > 0.55;
        pal.background = bg;
        pal.text = fg;
        pal.bar_background = Color::mix(bg, fg, 0.08, 0.93);
        pal.card_background = Color::mix(bg, fg, 0.14, 0.95);
        pal.surface_soft = pal.is_light ? Color{0.0, 0.0, 0.0, 0.08} : Color{1.0, 1.0, 1.0, 0.10};
        pal.surface_hover = pal.is_light ? Color{0.0, 0.0, 0.0, 0.16} : Color{1.0, 1.0, 1.0, 0.20};

        const auto wal_map = (theme.contains("pywalMap") && theme["pywalMap"].is_object())
                                 ? theme["pywalMap"]
                                 : nlohmann::json::object();

        auto map_color = [&](const char* token, const char* fallback_role, double alpha = 1.0) -> std::optional<Color> {
            std::string role = wal_map.value(token, std::string(fallback_role));
            if (role.empty()) return std::nullopt;
            if (role.front() == '#') return Color::from_hex(role, alpha);
            if (colors.contains(role) && colors[role].is_string()) {
                return Color::from_hex(colors[role].get<std::string>(), alpha);
            }
            return std::nullopt;
        };

        if (auto c = map_color("accent", "color1")) pal.accent = *c;
        if (auto c = map_color("accentHover", "color9")) pal.accent_hover = *c;
        if (auto c = map_color("selectionBorder", "color2")) pal.selection_border = *c;
        if (auto c = map_color("snapBorder", "color3")) pal.snap_border = *c;
        if (auto c = map_color("aiAccent", "color5")) pal.ai_accent = *c;
        if (auto c = map_color("pinBorder", "color4")) pal.pin_border = *c;
        if (auto c = map_color("danger", "color1")) pal.danger = *c;
        if (auto c = map_color("barBorder", "color8", 0.55)) pal.bar_border = *c;
        if (auto c = map_color("textSubtle", "color7", 0.80)) pal.text_subtle = *c;

        pal.on_accent = pal.accent.luminance() > 0.58 ? Color::from_hex("#111116") : Color::from_hex("#ffffff");

        for (const char* k : {"color1", "color3", "color2", "color4", "color5", "color6", "color7", "color0"}) {
            if (colors.contains(k) && colors[k].is_string()) {
                std::string v = colors[k].get<std::string>();
                if (!v.empty() && v.front() == '#') {
                    pal.satty_palette.push_back(v.substr(1) + "ff");
                }
            }
        }
    }

    if (theme.contains("overrides") && theme["overrides"].is_object()) {
        const auto& ov = theme["overrides"];
        auto apply_ov = [&](const char* k, Color& dst, double alpha = -1.0) {
            if (ov.contains(k) && ov[k].is_string()) {
                std::string s = trim_str(ov[k].get<std::string>());
                if (!s.empty()) dst = Color::from_hex(s, alpha >= 0.0 ? alpha : dst.a);
            }
        };
        apply_ov("background", pal.background);
        apply_ov("barBackground", pal.bar_background);
        apply_ov("cardBackground", pal.card_background);
        apply_ov("barBorder", pal.bar_border);
        apply_ov("accent", pal.accent, 1.0);
        apply_ov("accentHover", pal.accent_hover, 1.0);
        apply_ov("selectionBorder", pal.selection_border, 1.0);
        apply_ov("snapBorder", pal.snap_border, 1.0);
        apply_ov("aiAccent", pal.ai_accent, 1.0);
        apply_ov("pinBorder", pal.pin_border, 1.0);
        apply_ov("danger", pal.danger, 1.0);
        apply_ov("text", pal.text, 1.0);
        apply_ov("textSubtle", pal.text_subtle);
        apply_ov("onAccent", pal.on_accent, 1.0);
    }

    return pal;
}

nlohmann::json ConfigManager::palette_to_json(const ThemePalette& pal) {
    return nlohmann::json{
        {"source", pal.source},
        {"isLight", pal.is_light},
        {"background", pal.background.to_hex()},
        {"barBackground", pal.bar_background.to_hex()},
        {"cardBackground", pal.card_background.to_hex()},
        {"barBorder", pal.bar_border.to_hex()},
        {"accent", pal.accent.to_hex()},
        {"accentHover", pal.accent_hover.to_hex()},
        {"selectionBorder", pal.selection_border.to_hex()},
        {"snapBorder", pal.snap_border.to_hex()},
        {"aiAccent", pal.ai_accent.to_hex()},
        {"pinBorder", pal.pin_border.to_hex()},
        {"danger", pal.danger.to_hex()},
        {"text", pal.text.to_hex()},
        {"textSubtle", pal.text_subtle.to_hex()},
        {"onAccent", pal.on_accent.to_hex()},
        {"sattyPalette", pal.satty_palette},
    };
}

fs::path ConfigManager::export_satty_pywal_config(const nlohmann::json& cfg,
                                                  const std::string& output_path) {
    ThemePalette pal = resolve_palette(cfg);
    std::vector<std::string> colors = pal.satty_palette;
    if (colors.empty()) {
        colors = {"eb6960ff", "f3c568ff", "68df93ff", "6496ffff",
                  "955eedff", "df5eedff", "ebeaebff", "18121aff"};
    }
    fs::path target = output_path.empty() ? (resolve_cache_dir() / "satty-pywal.toml") : fs::path(output_path);
    std::error_code ec;
    fs::create_directories(target.parent_path(), ec);
    std::ofstream f(target, std::ios::binary | std::ios::trunc);
    f << "# Generated by HyprSmartShot Pywal theme sync\n[color-palette]\npalette = [\n";
    for (size_t i = 0; i < colors.size(); ++i) {
        std::string c = colors[i];
        if (!c.empty() && c.front() == '#') c.erase(c.begin());
        f << "    \"#" << c << "\"" << (i + 1 < colors.size() ? "," : "") << "\n";
    }
    f << "]\n";
    return target;
}

std::string ConfigManager::load_env_file_key(const std::string& env_name,
                                             const std::string& explicit_config) {
    if (env_name.empty()) return "";
    fs::path env_file = resolve_config_dir(explicit_config) / "api_keys.env";
    std::ifstream f(env_file);
    if (!f) return "";
    std::string line;
    while (std::getline(f, line)) {
        line = trim_str(line);
        if (line.empty() || line.front() == '#') continue;
        if (line.rfind("export ", 0) == 0) line = trim_str(line.substr(7));
        auto eq = line.find('=');
        if (eq == std::string::npos) continue;
        std::string k = trim_str(line.substr(0, eq));
        if (k != env_name) continue;
        std::string v = trim_str(line.substr(eq + 1));
        if (v.size() >= 2 && ((v.front() == '"' && v.back() == '"') ||
                              (v.front() == '\'' && v.back() == '\''))) {
            v = v.substr(1, v.size() - 2);
        }
        return v;
    }
    return "";
}

std::string ConfigManager::resolve_api_key(const nlohmann::json& prov_cfg,
                                           const std::string& explicit_config) {
    if (!prov_cfg.is_object()) return "";
    std::string direct = trim_str(prov_cfg.value("apiKey", std::string()));
    if (!direct.empty()) return direct;
    std::string env_name = trim_str(prov_cfg.value("apiKeyEnv", std::string()));
    if (env_name.empty()) return "";
    std::string env_val = trim_str(get_env_str(env_name.c_str()));
    if (!env_val.empty()) return env_val;
    return load_env_file_key(env_name, explicit_config);
}

std::string ConfigManager::resolve_preset_for_class(const nlohmann::json& cfg,
                                                    const std::string& window_class) {
    std::string active = cfg.value("activePreset", std::string("default"));
    if (window_class.empty() || !cfg.contains("appRules") || !cfg["appRules"].is_object()) {
        return active.empty() ? "default" : active;
    }
    std::string cls_low = to_lower_ascii(window_class);
    const auto& rules = cfg["appRules"];
    for (auto it = rules.begin(); it != rules.end(); ++it) {
        if (!it.value().is_string()) continue;
        std::string pattern = to_lower_ascii(it.key());
        if (cls_low == pattern || cls_low.find(pattern) != std::string::npos) {
            return it.value().get<std::string>();
        }
    }
    return active.empty() ? "default" : active;
}

}  // namespace hss
