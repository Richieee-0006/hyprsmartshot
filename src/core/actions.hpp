#pragma once

#include "core/config.hpp"
#include "core/i18n.hpp"
#include "core/image_ops.hpp"
#include "wayland/clipboard.hpp"

#include <filesystem>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace hss {

class Actions {
public:
    static bool command_exists(const std::string& cmd);
    static void spawn_detached(const std::vector<std::string>& argv);

    static void play_shutter();
    static void notify(const std::string& title,
                       const std::string& body,
                       const std::string& toast_type = "success",
                       const std::string& icon = "photo_camera",
                       const std::string& image_path = "");

    static void run_hook(const std::string& hook_template, const std::string& file_path);

    static void copy_crop(const PixelBuffer& cropped,
                          const nlohmann::json& cfg,
                          const I18n& i18n,
                          Clipboard* daemon_clipboard = nullptr);

    static std::filesystem::path save_crop(const PixelBuffer& cropped,
                                           const nlohmann::json& cfg,
                                           const I18n& i18n,
                                           bool is_fullscreen = false,
                                           Clipboard* daemon_clipboard = nullptr);

    static void pin_crop(const PixelBuffer& cropped,
                         int logical_x, int logical_y, int logical_w, int logical_h,
                         const ThemePalette& palette,
                         const I18n& i18n,
                         const std::string& self_exe = "");

    static void annotate_crop(const PixelBuffer& cropped,
                              const nlohmann::json& cfg,
                              const I18n& i18n);

    static void ocr_crop(const PixelBuffer& cropped,
                         const std::string& ocr_langs,
                         const nlohmann::json& cfg,
                         const I18n& i18n,
                         Clipboard* daemon_clipboard = nullptr);

    static void ai_vision_crop(const PixelBuffer& cropped,
                               const std::string& action_mode,
                               const nlohmann::json& cfg,
                               const I18n& i18n,
                               Clipboard* daemon_clipboard = nullptr);

    static void launch_settings_gui(const std::string& self_exe = "",
                                    const std::string& tab = "");

    static std::string timestamp_now();
};

}  // namespace hss
