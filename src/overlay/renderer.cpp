#include "overlay/renderer.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <pango/pangocairo.h>

namespace hss {

namespace {

void rounded_rect_path(cairo_t* cr, double x, double y, double w, double h, double r) {
    r = std::max(0.0, std::min({r, w * 0.5, h * 0.5}));
    constexpr double kPi = 3.14159265358979323846;
    cairo_new_path(cr);
    cairo_new_sub_path(cr);
    cairo_arc(cr, x + w - r, y + r, r, -kPi * 0.5, 0.0);
    cairo_arc(cr, x + w - r, y + h - r, r, 0.0, kPi * 0.5);
    cairo_arc(cr, x + r, y + h - r, r, kPi * 0.5, kPi);
    cairo_arc(cr, x + r, y + r, r, kPi, kPi * 1.5);
    cairo_close_path(cr);
}

void set_color(cairo_t* cr, const Color& c) {
    cairo_set_source_rgba(cr, c.r, c.g, c.b, c.a);
}

struct TextMeasure {
    double w = 0;
    double h = 0;
};

PangoLayout* make_layout(cairo_t* cr, const std::string& text,
                         const std::string& font_family, double px_size, bool bold = false) {
    PangoLayout* layout = pango_cairo_create_layout(cr);
    PangoFontDescription* desc = pango_font_description_new();
    pango_font_description_set_family(desc, font_family.c_str());
    pango_font_description_set_absolute_size(desc, px_size * PANGO_SCALE);
    pango_font_description_set_weight(desc, bold ? PANGO_WEIGHT_SEMIBOLD : PANGO_WEIGHT_NORMAL);
    pango_layout_set_font_description(layout, desc);
    pango_layout_set_text(layout, text.c_str(), static_cast<int>(text.size()));
    pango_font_description_free(desc);
    return layout;
}

TextMeasure measure_text(cairo_t* cr, const std::string& text,
                         const std::string& font_family, double px_size, bool bold = false) {
    PangoLayout* layout = make_layout(cr, text, font_family, px_size, bold);
    int tw = 0, th = 0;
    pango_layout_get_pixel_size(layout, &tw, &th);
    g_object_unref(layout);
    return {static_cast<double>(tw), static_cast<double>(th)};
}

void draw_text_centered(cairo_t* cr, const std::string& text,
                        double cx, double cy,
                        const std::string& font_family, double px_size,
                        const Color& col, bool bold = false) {
    PangoLayout* layout = make_layout(cr, text, font_family, px_size, bold);
    int tw = 0, th = 0;
    pango_layout_get_pixel_size(layout, &tw, &th);
    cairo_move_to(cr, cx - tw * 0.5, cy - th * 0.5);
    set_color(cr, col);
    pango_cairo_show_layout(cr, layout);
    g_object_unref(layout);
}

void draw_text_left(cairo_t* cr, const std::string& text,
                    double x, double cy,
                    const std::string& font_family, double px_size,
                    const Color& col, bool bold = false) {
    PangoLayout* layout = make_layout(cr, text, font_family, px_size, bold);
    int tw = 0, th = 0;
    pango_layout_get_pixel_size(layout, &tw, &th);
    cairo_move_to(cr, x, cy - th * 0.5);
    set_color(cr, col);
    pango_cairo_show_layout(cr, layout);
    g_object_unref(layout);
}

std::string candidate_tag_prefix(const CandidateBox& c, const I18n& i18n) {
    if (c.source == "ai" || c.type == "ai") return i18n.t("tagAi", "AI • ");
    if (c.type == "grid_container") return i18n.t("tagGrid", "Grid • ");
    if (c.type == "grid_row") return i18n.t("tagRow", "Row • ");
    if (c.type == "floating_window") return i18n.t("tagFloating", "Floating") + " • ";
    if (c.type == "window") return i18n.t("tagWindow", "Window") + " • ";
    if (c.type == "slot") return i18n.t("tagSlot", "Slot • ");
    if (c.type == "item") return i18n.t("tagItem", "Item • ");
    if (c.type == "panel") return i18n.t("tagPanel", "Panel • ");
    if (c.type == "button") return i18n.t("tagButton", "Button • ");
    if (c.type == "input") return i18n.t("tagInput", "Input • ");
    if (c.type == "text_block") return i18n.t("tagParagraph", "Paragraph • ");
    if (c.type == "text") return i18n.t("tagText", "Text • ");
    if (c.type == "screen") return i18n.t("tagScreen", "Screen • ");
    return "";
}

}  // namespace

void OverlayRenderer::render(uint8_t* dst_bgra, int phys_w, int phys_h, int dst_stride,
                             double scale,
                             const PixelBuffer& freeze_img,
                             const PixelBuffer& dimmed_img,
                             const SmartSelector& selector,
                             const OverlayUiState& ui,
                             const ThemePalette& pal,
                             const nlohmann::json& cfg,
                             const I18n& i18n) {
    hits_.clear();
    if (!dst_bgra || phys_w <= 0 || phys_h <= 0 || freeze_img.empty() || dimmed_img.empty()) return;

    const double s = (scale > 0.0) ? scale : 1.0;
    const double log_w = phys_w / s;
    const double log_h = phys_h / s;

    // 1. Blit pre-baked dimmed backdrop directly (zero Cairo overhead on full frame!)
    if (dimmed_img.width == phys_w && dimmed_img.height == phys_h && dimmed_img.stride == dst_stride) {
        std::memcpy(dst_bgra, dimmed_img.data.data(), static_cast<size_t>(dst_stride) * phys_h);
    } else {
        cairo_surface_t* dst_s = cairo_image_surface_create_for_data(
            dst_bgra, CAIRO_FORMAT_RGB24, phys_w, phys_h, dst_stride);
        cairo_surface_t* dim_s = cairo_image_surface_create_for_data(
            const_cast<uint8_t*>(dimmed_img.data.data()), CAIRO_FORMAT_RGB24,
            dimmed_img.width, dimmed_img.height, dimmed_img.stride);
        cairo_t* cr0 = cairo_create(dst_s);
        cairo_scale(cr0, static_cast<double>(phys_w) / dimmed_img.width,
                    static_cast<double>(phys_h) / dimmed_img.height);
        cairo_set_source_surface(cr0, dim_s, 0, 0);
        cairo_paint(cr0);
        cairo_destroy(cr0);
        cairo_surface_destroy(dim_s);
        cairo_surface_destroy(dst_s);
    }

    cairo_surface_t* surface = cairo_image_surface_create_for_data(
        dst_bgra, CAIRO_FORMAT_ARGB32, phys_w, phys_h, dst_stride);
    cairo_t* cr = cairo_create(surface);
    cairo_scale(cr, s, s);

    // 2. Un-dimmed sharp selection cutout + selection border + resize handles
    if (selector.has_selection()) {
        double sx = selector.sel_x();
        double sy = selector.sel_y();
        double sw = selector.sel_w();
        double sh = selector.sel_h();
        double rad = (sw >= log_w - 2 && sh >= log_h - 2) ? 0.0 : pal.border_radius;

        cairo_surface_t* raw_s = cairo_image_surface_create_for_data(
            const_cast<uint8_t*>(freeze_img.data.data()), CAIRO_FORMAT_RGB24,
            freeze_img.width, freeze_img.height, freeze_img.stride);
        cairo_save(cr);
        rounded_rect_path(cr, sx, sy, sw, sh, rad);
        cairo_clip(cr);
        cairo_scale(cr, log_w / freeze_img.width, log_h / freeze_img.height);
        cairo_set_source_surface(cr, raw_s, 0, 0);
        cairo_paint(cr);
        cairo_restore(cr);
        cairo_surface_destroy(raw_s);

        const CandidateBox* cand = selector.selected_candidate();
        bool is_ai = (cand && (cand->source == "ai" || cand->type == "ai"));
        Color border_c = selector.is_confirmed()
                             ? pal.selection_border
                             : (is_ai ? pal.ai_accent : pal.accent);

        rounded_rect_path(cr, sx, sy, sw, sh, rad);
        set_color(cr, border_c);
        cairo_set_line_width(cr, pal.outline_thickness);
        cairo_stroke(cr);

        // 8 crisp resize handles when confirmed
        if (selector.is_confirmed()) {
            const double hs = 8.0;
            const double cx = sx + sw * 0.5;
            const double cy = sy + sh * 0.5;
            const double pts[8][2] = {
                {sx, sy}, {cx, sy}, {sx + sw, sy}, {sx + sw, cy},
                {sx + sw, sy + sh}, {cx, sy + sh}, {sx, sy + sh}, {sx, cy},
            };
            for (const auto& pt : pts) {
                rounded_rect_path(cr, pt[0] - hs * 0.5, pt[1] - hs * 0.5, hs, hs, 2.0);
                set_color(cr, pal.text);
                cairo_fill_preserve(cr);
                set_color(cr, border_c);
                cairo_set_line_width(cr, 1.5);
                cairo_stroke(cr);
            }
        }

        // Hover candidate label + confidence pill (above top-left of selection)
        if (!selector.is_confirmed() && !selector.is_dragging() && cand) {
            std::string tag = candidate_tag_prefix(*cand, i18n) +
                              std::to_string(static_cast<int>(std::lround(sw))) + " × " +
                              std::to_string(static_cast<int>(std::lround(sh)));
            if (ui.show_confidence && cand->source != "screen") {
                tag += "  " + std::to_string(cand->score) + "%";
            }
            if (selector.hierarchy().size() > 1) {
                tag += "  " + std::to_string(selector.hierarchy_index() + 1) + "/" +
                       std::to_string(selector.hierarchy().size()) + " " + i18n.t("scrollHint", "[Scroll]");
            }
            auto tm = measure_text(cr, tag, pal.font_family, 11.0, true);
            double pw = tm.w + 16.0;
            double ph = 24.0;
            double px = std::clamp(sx, 8.0, std::max(8.0, log_w - pw - 8.0));
            double py = (sy >= ph + 10.0) ? (sy - ph - 6.0) : (sy + 8.0);
            rounded_rect_path(cr, px, py, pw, ph, 6.0);
            set_color(cr, pal.bar_background);
            cairo_fill_preserve(cr);
            set_color(cr, border_c.with_alpha(0.75));
            cairo_set_line_width(cr, 1.0);
            cairo_stroke(cr);
            draw_text_centered(cr, tag, px + pw * 0.5, py + ph * 0.5, pal.font_family, 11.0, pal.text, true);
        }
    }

    // 3. Top ControlBar (4px grid: height 44, top margin 20)
    {
        const double bar_h = 44.0;
        const double mode_w = 108.0;
        const double preset_w = 112.0;
        const double icon_w = 36.0;
        const double gap = 4.0;
        const double pad = 4.0;
        const double bar_w = pad * 2 + mode_w * 2 + gap * 6 + preset_w + icon_w * 4;
        const double bx = (log_w - bar_w) * 0.5;
        const double by = 20.0;

        rounded_rect_path(cr, bx, by, bar_w, bar_h, bar_h * 0.5);
        set_color(cr, pal.bar_background);
        cairo_fill_preserve(cr);
        set_color(cr, pal.bar_border);
        cairo_set_line_width(cr, 1.0);
        cairo_stroke(cr);
        hits_.push_back({bx, by, bar_w, bar_h, UiHitKind::ControlBarBg, ""});

        double cx = bx + pad;
        const double cy = by + pad;
        const double ih = bar_h - pad * 2;

        auto draw_pill_btn = [&](double w, const std::string& label, bool active,
                                 const Color& active_col, UiHitKind kind, const std::string& val = "") {
            bool hovered = (ui.hover_x >= cx && ui.hover_x <= cx + w &&
                            ui.hover_y >= cy && ui.hover_y <= cy + ih);
            if (active || hovered) {
                rounded_rect_path(cr, cx, cy, w, ih, ih * 0.5);
                set_color(cr, active ? active_col : pal.surface_hover);
                cairo_fill(cr);
            } else if (kind != UiHitKind::ModeSmart && kind != UiHitKind::ModeScreen) {
                rounded_rect_path(cr, cx, cy, w, ih, ih * 0.5);
                set_color(cr, pal.surface_soft);
                cairo_fill(cr);
            }
            Color tc = active ? pal.on_accent : (kind == UiHitKind::CloseBtn ? pal.danger : pal.text);
            draw_text_centered(cr, label, cx + w * 0.5, cy + ih * 0.5, pal.font_family, 12.0, tc, active);
            hits_.push_back({cx, cy, w, ih, kind, val});
            cx += w + gap;
        };

        draw_pill_btn(mode_w, "󰓥 " + i18n.t("modeSmart", "Smart"),
                      selector.mode() != "screen", pal.accent, UiHitKind::ModeSmart);
        draw_pill_btn(mode_w, "󰍹 " + i18n.t("modeScreen", "Screen"),
                      selector.mode() == "screen", pal.accent, UiHitKind::ModeScreen);

        // Preset dropdown button
        double preset_x = cx;
        std::string preset_label = selector.active_preset();
        if (cfg.contains("presets") && cfg["presets"].contains(preset_label) &&
            cfg["presets"][preset_label].contains("name")) {
            preset_label = cfg["presets"][preset_label]["name"].get<std::string>();
        }
        draw_pill_btn(preset_w, preset_label + " ▾", ui.preset_menu_open,
                      pal.surface_hover, UiHitKind::PresetToggle);

        draw_pill_btn(icon_w, "󰍉", ui.magnifier_active, pal.accent, UiHitKind::MagnifierToggle);
        draw_pill_btn(icon_w, ui.ai_loading ? "…" : "󰚩",
                      selector.ai_active() || ui.ai_loading, pal.ai_accent, UiHitKind::AiDetect);
        draw_pill_btn(icon_w, "󰒓", false, pal.surface_hover, UiHitKind::SettingsBtn);
        draw_pill_btn(icon_w, "✕", false, pal.danger, UiHitKind::CloseBtn);

        // Preset dropdown popup
        if (ui.preset_menu_open && cfg.contains("presets") && cfg["presets"].is_object()) {
            const auto& presets = cfg["presets"];
            double item_h = 32.0;
            double pop_w = 148.0;
            double pop_h = presets.size() * item_h + 8.0;
            double pop_x = preset_x;
            double pop_y = by + bar_h + 8.0;
            rounded_rect_path(cr, pop_x, pop_y, pop_w, pop_h, 10.0);
            set_color(cr, pal.card_background);
            cairo_fill_preserve(cr);
            set_color(cr, pal.bar_border);
            cairo_set_line_width(cr, 1.0);
            cairo_stroke(cr);

            double iy = pop_y + 4.0;
            for (auto it = presets.begin(); it != presets.end(); ++it) {
                std::string k = it.key();
                std::string nm = it.value().value("name", k);
                bool cur = (k == selector.active_preset());
                bool hov = (ui.hover_x >= pop_x + 4 && ui.hover_x <= pop_x + pop_w - 4 &&
                            ui.hover_y >= iy && ui.hover_y <= iy + item_h);
                if (cur || hov) {
                    rounded_rect_path(cr, pop_x + 4, iy, pop_w - 8, item_h, 6.0);
                    set_color(cr, cur ? pal.accent : pal.surface_hover);
                    cairo_fill(cr);
                }
                draw_text_left(cr, nm, pop_x + 14, iy + item_h * 0.5, pal.font_family, 12.0,
                               cur ? pal.on_accent : pal.text, cur);
                hits_.push_back({pop_x + 4, iy, pop_w - 8, item_h, UiHitKind::PresetOption, k});
                iy += item_h;
            }
        }
    }

    // 4. Floating ActionPill (when confirmed)
    if (selector.is_confirmed() && selector.has_selection()) {
        const auto ai_enabled = cfg.contains("ai") && cfg["ai"].is_object() && cfg["ai"].value("enabled", false);
        const auto rating_enabled = !(cfg.contains("rating") && cfg["rating"].is_object() &&
                                      cfg["rating"].value("enabled", true) == false);
        const CandidateBox* cand = selector.selected_candidate();
        const bool can_rate = rating_enabled && cand && (cand->source == "cv" || cand->source == "ai");

        struct BtnSpec {
            std::string label;
            UiHitKind kind;
            bool primary = false;
            bool accent_ai = false;
            bool danger = false;
            double width = 0;
        };

        std::string dim_txt = std::to_string(static_cast<int>(std::lround(selector.sel_w()))) + " × " +
                              std::to_string(static_cast<int>(std::lround(selector.sel_h())));
        auto dim_m = measure_text(cr, dim_txt, pal.font_family, 11.0, true);
        double dim_w = dim_m.w + 16.0;

        std::vector<BtnSpec> btns = {
            {"󰆏 " + i18n.t("copy", "Copy"), UiHitKind::ActionCopy, true, false, false, 0},
            {"󰆓 " + i18n.t("save", "Save"), UiHitKind::ActionSave, false, false, false, 0},
            {"󰐃 " + i18n.t("pin", "Pin"), UiHitKind::ActionPin, false, false, false, 0},
            {"󰏫 " + i18n.t("annotate", "Annotate"), UiHitKind::ActionAnnotate, false, false, false, 0},
            {"󰉐 " + i18n.t("ocr", "OCR"), UiHitKind::ActionOcr, false, false, false, 0},
            {ui.ocr_lang + " ▾", UiHitKind::ActionOcrMenu, false, false, false, 0},
        };
        if (ai_enabled) {
            btns.push_back({"󰚩 " + i18n.t("aiAction", "AI ▾"), UiHitKind::ActionAiMenu, false, true, false, 0});
        }
        if (can_rate) {
            btns.push_back({"+", UiHitKind::ActionRateUp, false, false, false, 28.0});
            btns.push_back({"−", UiHitKind::ActionRateDown, false, false, false, 28.0});
        }
        btns.push_back({"✕", UiHitKind::ActionCancel, false, false, true, 28.0});

        double total_w = 12.0 + dim_w + 12.0;
        for (auto& b : btns) {
            if (b.width <= 0) {
                auto tm = measure_text(cr, b.label, pal.font_family, 12.0, b.primary);
                b.width = tm.w + 18.0;
            }
            total_w += b.width + 6.0;
        }
        total_w += 6.0;

        const double pill_h = 44.0;
        double px = std::clamp(selector.sel_x() + (selector.sel_w() - total_w) * 0.5,
                               12.0, std::max(12.0, log_w - total_w - 12.0));
        double py = selector.sel_y() + selector.sel_h() + 12.0;
        if (py + pill_h > log_h - 56.0) {
            py = selector.sel_y() - pill_h - 12.0;
        }
        if (py < 76.0) {
            py = std::clamp(selector.sel_y() + selector.sel_h() - pill_h - 12.0, 76.0, log_h - pill_h - 56.0);
        }

        rounded_rect_path(cr, px, py, total_w, pill_h, pill_h * 0.5);
        set_color(cr, pal.bar_background);
        cairo_fill_preserve(cr);
        set_color(cr, pal.selection_border);
        cairo_set_line_width(cr, 1.5);
        cairo_stroke(cr);
        hits_.push_back({px, py, total_w, pill_h, UiHitKind::ActionPillBg, ""});

        double cx = px + 10.0;
        double cy = py + 8.0;
        const double bh = 28.0;

        rounded_rect_path(cr, cx, cy, dim_w, bh, 6.0);
        set_color(cr, pal.surface_soft);
        cairo_fill(cr);
        draw_text_centered(cr, dim_txt, cx + dim_w * 0.5, cy + bh * 0.5, pal.font_family, 11.0, pal.text_subtle, true);
        cx += dim_w + 10.0;

        double ocr_menu_x = 0.0;
        double ai_menu_x = 0.0;

        for (const auto& b : btns) {
            bool hov = (ui.hover_x >= cx && ui.hover_x <= cx + b.width &&
                        ui.hover_y >= cy && ui.hover_y <= cy + bh);
            if (b.kind == UiHitKind::ActionOcrMenu) ocr_menu_x = cx;
            if (b.kind == UiHitKind::ActionAiMenu) ai_menu_x = cx;

            rounded_rect_path(cr, cx, cy, b.width, bh, bh * 0.5);
            if (b.primary) {
                set_color(cr, hov ? pal.accent_hover : pal.accent);
                cairo_fill(cr);
            } else if (b.accent_ai) {
                set_color(cr, hov ? pal.ai_accent : pal.ai_accent.with_alpha(0.28));
                cairo_fill(cr);
            } else if (hov) {
                set_color(cr, b.danger ? pal.danger.with_alpha(0.28) : pal.surface_hover);
                cairo_fill(cr);
            } else {
                set_color(cr, pal.surface_soft);
                cairo_fill(cr);
            }
            Color tc = b.primary ? pal.on_accent : (b.danger ? pal.danger : pal.text);
            draw_text_centered(cr, b.label, cx + b.width * 0.5, cy + bh * 0.5, pal.font_family, 12.0, tc, b.primary);
            hits_.push_back({cx, cy, b.width, bh, b.kind, ""});
            cx += b.width + 6.0;
        }

        // OCR language dropdown
        if (ui.ocr_menu_open) {
            const std::pair<const char*, const char*> langs[] = {
                {"eng", "English (eng)"},
                {"ces", "Čeština (ces)"},
                {"eng+ces", "English + Čeština"},
            };
            double mw = 168.0, ih = 30.0, mh = 3 * ih + 8.0;
            double mx = std::clamp(ocr_menu_x, 8.0, log_w - mw - 8.0);
            double my = (py + pill_h + mh + 8.0 <= log_h) ? (py + pill_h + 6.0) : (py - mh - 6.0);
            rounded_rect_path(cr, mx, my, mw, mh, 10.0);
            set_color(cr, pal.card_background);
            cairo_fill_preserve(cr);
            set_color(cr, pal.bar_border);
            cairo_set_line_width(cr, 1.0);
            cairo_stroke(cr);
            double iy = my + 4.0;
            for (const auto& [code, label] : langs) {
                bool cur = (ui.ocr_lang == code);
                bool hov = (ui.hover_x >= mx + 4 && ui.hover_x <= mx + mw - 4 &&
                            ui.hover_y >= iy && ui.hover_y <= iy + ih);
                if (cur || hov) {
                    rounded_rect_path(cr, mx + 4, iy, mw - 8, ih, 6.0);
                    set_color(cr, cur ? pal.accent : pal.surface_hover);
                    cairo_fill(cr);
                }
                draw_text_left(cr, label, mx + 12, iy + ih * 0.5, pal.font_family, 11.5,
                               cur ? pal.on_accent : pal.text, cur);
                hits_.push_back({mx + 4, iy, mw - 8, ih, UiHitKind::ActionOcrLang, code});
                iy += ih;
            }
        }

        // AI Vision action dropdown
        if (ui.ai_menu_open && ai_enabled) {
            const std::pair<UiHitKind, std::string> items[] = {
                {UiHitKind::ActionAiOcr, "󰉐 " + i18n.t("aiOcr", "AI OCR")},
                {UiHitKind::ActionAiDescribe, "󰋼 " + i18n.t("aiDescribe", "AI Describe")},
            };
            double mw = 152.0, ih = 30.0, mh = 2 * ih + 8.0;
            double mx = std::clamp(ai_menu_x, 8.0, log_w - mw - 8.0);
            double my = (py + pill_h + mh + 8.0 <= log_h) ? (py + pill_h + 6.0) : (py - mh - 6.0);
            rounded_rect_path(cr, mx, my, mw, mh, 10.0);
            set_color(cr, pal.card_background);
            cairo_fill_preserve(cr);
            set_color(cr, pal.ai_accent);
            cairo_set_line_width(cr, 1.0);
            cairo_stroke(cr);
            double iy = my + 4.0;
            for (const auto& [kind, label] : items) {
                bool hov = (ui.hover_x >= mx + 4 && ui.hover_x <= mx + mw - 4 &&
                            ui.hover_y >= iy && ui.hover_y <= iy + ih);
                if (hov) {
                    rounded_rect_path(cr, mx + 4, iy, mw - 8, ih, 6.0);
                    set_color(cr, pal.ai_accent.with_alpha(0.35));
                    cairo_fill(cr);
                }
                draw_text_left(cr, label, mx + 12, iy + ih * 0.5, pal.font_family, 11.5, pal.text, false);
                hits_.push_back({mx + 4, iy, mw - 8, ih, kind, ""});
                iy += ih;
            }
        }
    }

    // 5. Circular Magnifier Loupe (nearest-neighbor direct from in-RAM BGRA freeze buffer)
    if (ui.magnifier_active) {
        double d = std::clamp(ui.magnifier_size, 100.0, 260.0);
        double rad = d * 0.5;
        double zoom = std::clamp(ui.magnifier_zoom, 1.5, 8.0);
        double lx = std::clamp(selector.cursor_x() + 24.0, 12.0, std::max(12.0, log_w - d - 12.0));
        double ly = std::clamp(selector.cursor_y() + 24.0, 12.0, std::max(12.0, log_h - d - 12.0));
        double mcx = lx + rad;
        double mcy = ly + rad;

        cairo_surface_t* raw_s = cairo_image_surface_create_for_data(
            const_cast<uint8_t*>(freeze_img.data.data()), CAIRO_FORMAT_RGB24,
            freeze_img.width, freeze_img.height, freeze_img.stride);

        cairo_save(cr);
        cairo_arc(cr, mcx, mcy, rad, 0.0, 6.283185307179586);
        cairo_clip(cr);
        set_color(cr, pal.card_background);
        cairo_paint(cr);

        double fx = selector.cursor_x() * (freeze_img.width / log_w);
        double fy = selector.cursor_y() * (freeze_img.height / log_h);
        cairo_translate(cr, mcx, mcy);
        cairo_scale(cr, zoom * (log_w / freeze_img.width), zoom * (log_h / freeze_img.height));
        cairo_translate(cr, -fx, -fy);
        cairo_set_source_surface(cr, raw_s, 0, 0);
        cairo_pattern_set_filter(cairo_get_source(cr), CAIRO_FILTER_NEAREST);
        cairo_paint(cr);
        cairo_restore(cr);
        cairo_surface_destroy(raw_s);

        // Crosshair
        set_color(cr, pal.accent);
        cairo_set_line_width(cr, 1.5);
        cairo_move_to(cr, mcx - 8, mcy); cairo_line_to(cr, mcx + 8, mcy);
        cairo_move_to(cr, mcx, mcy - 8); cairo_line_to(cr, mcx, mcy + 8);
        cairo_stroke(cr);

        // Ring border
        cairo_arc(cr, mcx, mcy, rad, 0.0, 6.283185307179586);
        set_color(cr, pal.accent);
        cairo_set_line_width(cr, 2.5);
        cairo_stroke(cr);

        // Coordinates badge
        std::string coord = std::to_string(static_cast<int>(std::lround(selector.cursor_x()))) + ", " +
                            std::to_string(static_cast<int>(std::lround(selector.cursor_y())));
        auto cm = measure_text(cr, coord, pal.font_family, 10.0, true);
        double bw = cm.w + 12.0, bh = 18.0;
        rounded_rect_path(cr, mcx - bw * 0.5, ly + d - bh - 8.0, bw, bh, 9.0);
        set_color(cr, pal.bar_background);
        cairo_fill(cr);
        draw_text_centered(cr, coord, mcx, ly + d - bh * 0.5 - 8.0, pal.font_family, 10.0, pal.text, true);
    }

    // 6. Status Toast Banner (below ControlBar)
    if (!ui.status_toast.empty()) {
        auto tm = measure_text(cr, ui.status_toast, pal.font_family, 11.5, true);
        double tw = tm.w + 24.0;
        double th = 28.0;
        double tx = (log_w - tw) * 0.5;
        double ty = 74.0;
        rounded_rect_path(cr, tx, ty, tw, th, 14.0);
        set_color(cr, pal.bar_background);
        cairo_fill_preserve(cr);
        set_color(cr, pal.ai_accent);
        cairo_set_line_width(cr, 1.0);
        cairo_stroke(cr);
        draw_text_centered(cr, ui.status_toast, tx + tw * 0.5, ty + th * 0.5, pal.font_family, 11.5, pal.text, true);
    }

    // 7. Bottom Hint Bar
    if (ui.show_hints) {
        std::string hint = selector.is_confirmed()
                               ? i18n.t("hintConfirmed", "[Enter] Copy • [Ctrl+S] Save • [P] Pin • [A] Annotate • [O] OCR • [Esc] Back")
                               : i18n.t("hintUnconfirmed", "[Click] Select • [Drag] Region • [Scroll/Tab] Cycle • [I] AI • [,] Settings • [Alt] Loupe • [Esc] Close");
        auto hm = measure_text(cr, hint, pal.font_family, 11.0, false);
        double hw = std::min(log_w - 24.0, hm.w + 24.0);
        double hh = 28.0;
        double hx = (log_w - hw) * 0.5;
        double hy = log_h - hh - 16.0;
        rounded_rect_path(cr, hx, hy, hw, hh, 14.0);
        set_color(cr, pal.bar_background);
        cairo_fill_preserve(cr);
        set_color(cr, pal.bar_border);
        cairo_set_line_width(cr, 1.0);
        cairo_stroke(cr);
        draw_text_centered(cr, hint, hx + hw * 0.5, hy + hh * 0.5, pal.font_family, 11.0, pal.text_subtle, false);
    }

    cairo_destroy(cr);
    cairo_surface_destroy(surface);
}

UiHitRect OverlayRenderer::hit_test(double logical_x, double logical_y) const {
    // Iterate in reverse so topmost popups & buttons win over pill backgrounds
    for (auto it = hits_.rbegin(); it != hits_.rend(); ++it) {
        if (it->contains(logical_x, logical_y)) return *it;
    }
    return {};
}

bool OverlayRenderer::point_in_chrome(double logical_x, double logical_y) const {
    return hit_test(logical_x, logical_y).kind != UiHitKind::None;
}

}  // namespace hss
