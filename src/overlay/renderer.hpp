#pragma once

#include "core/config.hpp"
#include "core/i18n.hpp"
#include "core/image_ops.hpp"
#include "overlay/selector.hpp"

#include <cairo/cairo.h>
#include <string>
#include <vector>

namespace hss {

enum class UiHitKind {
    None,
    ControlBarBg,
    ModeSmart,
    ModeScreen,
    PresetToggle,
    PresetOption,
    MagnifierToggle,
    AiDetect,
    SettingsBtn,
    CloseBtn,
    ActionPillBg,
    ActionCopy,
    ActionSave,
    ActionPin,
    ActionAnnotate,
    ActionOcr,
    ActionOcrMenu,
    ActionOcrLang,
    ActionAiMenu,
    ActionAiOcr,
    ActionAiDescribe,
    ActionRateUp,
    ActionRateDown,
    ActionCancel,
};

struct UiHitRect {
    double x = 0;
    double y = 0;
    double w = 0;
    double h = 0;
    UiHitKind kind = UiHitKind::None;
    std::string value;

    bool contains(double px, double py) const {
        return px >= x && px <= x + w && py >= y && py <= y + h;
    }
};

struct OverlayUiState {
    bool magnifier_active = false;
    bool preset_menu_open = false;
    bool ocr_menu_open = false;
    bool ai_menu_open = false;
    bool ai_loading = false;
    bool show_hints = true;
    bool show_confidence = true;
    double magnifier_zoom = 3.0;
    double magnifier_size = 180.0;
    std::string ocr_lang = "eng";
    std::string status_toast;
    double hover_x = -1.0;
    double hover_y = -1.0;
};

class OverlayRenderer {
public:
    void render(uint8_t* dst_bgra, int phys_w, int phys_h, int dst_stride,
                double scale,
                const PixelBuffer& freeze_img,
                const PixelBuffer& dimmed_img,
                const SmartSelector& selector,
                const OverlayUiState& ui,
                const ThemePalette& pal,
                const nlohmann::json& cfg,
                const I18n& i18n);

    UiHitRect hit_test(double logical_x, double logical_y) const;
    bool point_in_chrome(double logical_x, double logical_y) const;

private:
    std::vector<UiHitRect> hits_;
};

}  // namespace hss
