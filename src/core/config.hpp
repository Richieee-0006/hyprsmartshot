#pragma once

#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace hss {

struct Color {
    double r = 0.0;
    double g = 0.0;
    double b = 0.0;
    double a = 1.0;

    static Color from_hex(const std::string& hex, double alpha = 1.0);
    std::string to_hex() const;
    double luminance() const { return 0.299 * r + 0.587 * g + 0.114 * b; }
    Color with_alpha(double alpha) const { return {r, g, b, alpha}; }
    static Color mix(const Color& a, const Color& b, double t, double alpha = 1.0);
};

struct ThemePalette {
    std::string source = "static";
    bool is_light = false;
    Color background = Color::from_hex("#141419", 0.88);
    Color bar_background = Color::from_hex("#1e1e26", 0.92);
    Color card_background = Color::from_hex("#282833", 0.94);
    Color bar_border = Color::from_hex("#45475a", 0.70);
    Color surface_soft = {1.0, 1.0, 1.0, 0.10};
    Color surface_hover = {1.0, 1.0, 1.0, 0.20};
    Color accent = Color::from_hex("#eb6960");
    Color accent_hover = Color::from_hex("#f2857d");
    Color on_accent = Color::from_hex("#ffffff");
    Color selection_border = Color::from_hex("#68df93");
    Color snap_border = Color::from_hex("#f3c568");
    Color ai_accent = Color::from_hex("#955eed");
    Color pin_border = Color::from_hex("#6496ff");
    Color danger = Color::from_hex("#ff6b6b");
    Color text = Color::from_hex("#ffffff");
    Color text_subtle = Color::from_hex("#b8b8c4", 0.80);

    double dim_opacity = 0.65;
    double border_radius = 10.0;
    double outline_thickness = 2.0;
    double pin_border_width = 2.0;
    std::string font_family = "JetBrainsMono Nerd Font";
    std::vector<std::string> satty_palette;
};

class ConfigManager {
public:
    static nlohmann::json default_config();
    static nlohmann::json deep_merge(const nlohmann::json& base, const nlohmann::json& patch);

    static std::string expand_home(const std::string& path);
    static std::filesystem::path resolve_data_dir(const std::string& exe_path = "");
    static std::filesystem::path resolve_config_dir(const std::string& explicit_config = "");
    static std::filesystem::path resolve_config_path(const std::string& explicit_config = "");
    static std::filesystem::path resolve_state_dir();
    static std::filesystem::path resolve_cache_dir();
    static std::filesystem::path resolve_save_dir(const nlohmann::json& cfg);

    static nlohmann::json load_config(const std::string& explicit_config = "",
                                      const nlohmann::json& cli_overrides = nlohmann::json());
    static std::filesystem::path save_user_config(const nlohmann::json& data,
                                                  const std::string& explicit_config = "");
    static std::filesystem::path patch_user_config(const nlohmann::json& patch,
                                                   const std::string& explicit_config = "");

    static ThemePalette resolve_palette(const nlohmann::json& cfg);
    static nlohmann::json palette_to_json(const ThemePalette& pal);
    static std::filesystem::path export_satty_pywal_config(const nlohmann::json& cfg,
                                                           const std::string& output_path = "");

    static std::string load_env_file_key(const std::string& env_name,
                                         const std::string& explicit_config = "");
    static std::string resolve_api_key(const nlohmann::json& prov_cfg,
                                       const std::string& explicit_config = "");
    static std::string resolve_preset_for_class(const nlohmann::json& cfg,
                                                const std::string& window_class);

private:
    static std::optional<nlohmann::json> read_json_file(const std::filesystem::path& p);
    static void apply_module_files_and_dropins(nlohmann::json& cfg, const std::filesystem::path& dir);
};

}  // namespace hss
