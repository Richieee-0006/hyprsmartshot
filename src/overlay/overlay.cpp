#include "overlay/overlay.hpp"
#include "core/actions.hpp"
#include "core/image_ops.hpp"
#include "overlay/renderer.hpp"
#include "overlay/selector.hpp"
#include "vision/rating.hpp"
#include "vision/vision_bridge.hpp"
#include "wayland/shm.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>
#include <iostream>
#include <linux/input-event-codes.h>
#include <malloc.h>
#include <memory>
#include <poll.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <unistd.h>
#include <xkbcommon/xkbcommon.h>

#include "cursor-shape-v1-client-protocol.h"
#include "fractional-scale-v1-client-protocol.h"
#include "viewporter-client-protocol.h"
#define namespace wl_namespace
#include "wlr-layer-shell-unstable-v1-client-protocol.h"
#undef namespace
#include "wlr-screencopy-unstable-v1-client-protocol.h"
#if HSS_HAVE_EXT_IMAGE_COPY_CAPTURE
#include "ext-image-capture-source-v1-client-protocol.h"
#include "ext-image-copy-capture-v1-client-protocol.h"
#endif

namespace hss {

namespace {

struct StandaloneWl {
    WaylandSharedGlobals g;
    wl_registry* registry = nullptr;

    bool connect() {
        g.display = wl_display_connect(nullptr);
        if (!g.display) return false;
        g.outputs.reserve(16);

        static const wl_output_listener out_l = {
            .geometry = [](void* data, wl_output*, int32_t x, int32_t y, int32_t, int32_t,
                           int32_t, const char*, const char*, int32_t tr) {
                auto* o = static_cast<WaylandOutput*>(data);
                o->x = x; o->y = y; o->transform = tr;
            },
            .mode = [](void* data, wl_output*, uint32_t flags, int32_t w, int32_t h, int32_t) {
                if (flags & WL_OUTPUT_MODE_CURRENT) {
                    auto* o = static_cast<WaylandOutput*>(data);
                    o->width = w; o->height = h;
                }
            },
            .done = [](void*, wl_output*) {},
            .scale = [](void* data, wl_output*, int32_t factor) {
                static_cast<WaylandOutput*>(data)->scale = factor;
            },
            .name = [](void* data, wl_output*, const char* name) {
                if (name) static_cast<WaylandOutput*>(data)->name = name;
            },
            .description = [](void*, wl_output*, const char*) {},
        };

        registry = wl_display_get_registry(g.display);
        static const wl_registry_listener reg_l = {
            .global = [](void* data, wl_registry* r, uint32_t name, const char* iface, uint32_t ver) {
                auto* c = static_cast<WaylandSharedGlobals*>(data);
                if (std::strcmp(iface, wl_compositor_interface.name) == 0) {
                    c->compositor = static_cast<wl_compositor*>(
                        wl_registry_bind(r, name, &wl_compositor_interface, std::min(ver, 5u)));
                } else if (std::strcmp(iface, wl_shm_interface.name) == 0) {
                    c->shm = static_cast<wl_shm*>(wl_registry_bind(r, name, &wl_shm_interface, 1));
                } else if (std::strcmp(iface, wl_seat_interface.name) == 0) {
                    c->seat = static_cast<wl_seat*>(
                        wl_registry_bind(r, name, &wl_seat_interface, std::min(ver, 7u)));
                } else if (std::strcmp(iface, wl_output_interface.name) == 0 && c->outputs.size() < 16) {
                    WaylandOutput wo;
                    wo.global_name = name;
                    wo.output = static_cast<wl_output*>(
                        wl_registry_bind(r, name, &wl_output_interface, std::min(ver, 4u)));
                    c->outputs.push_back(wo);
                    wl_output_add_listener(c->outputs.back().output, &out_l, &c->outputs.back());
                } else if (std::strcmp(iface, zwlr_layer_shell_v1_interface.name) == 0) {
                    c->layer_shell = static_cast<zwlr_layer_shell_v1*>(
                        wl_registry_bind(r, name, &zwlr_layer_shell_v1_interface, std::min(ver, 4u)));
                } else if (std::strcmp(iface, zwlr_screencopy_manager_v1_interface.name) == 0) {
                    c->wlr_screencopy_mgr = static_cast<zwlr_screencopy_manager_v1*>(
                        wl_registry_bind(r, name, &zwlr_screencopy_manager_v1_interface, std::min(ver, 3u)));
                } else if (std::strcmp(iface, wp_viewporter_interface.name) == 0) {
                    c->viewporter = static_cast<wp_viewporter*>(
                        wl_registry_bind(r, name, &wp_viewporter_interface, 1));
                } else if (std::strcmp(iface, wp_fractional_scale_manager_v1_interface.name) == 0) {
                    c->frac_mgr = static_cast<wp_fractional_scale_manager_v1*>(
                        wl_registry_bind(r, name, &wp_fractional_scale_manager_v1_interface, 1));
                } else if (std::strcmp(iface, wp_cursor_shape_manager_v1_interface.name) == 0) {
                    c->cursor_mgr = static_cast<wp_cursor_shape_manager_v1*>(
                        wl_registry_bind(r, name, &wp_cursor_shape_manager_v1_interface, 1));
                }
#if HSS_HAVE_EXT_IMAGE_COPY_CAPTURE
                else if (std::strcmp(iface, ext_image_copy_capture_manager_v1_interface.name) == 0) {
                    c->ext_capture_mgr = static_cast<ext_image_copy_capture_manager_v1*>(
                        wl_registry_bind(r, name, &ext_image_copy_capture_manager_v1_interface, 1));
                } else if (std::strcmp(iface, ext_output_image_capture_source_manager_v1_interface.name) == 0) {
                    c->ext_source_mgr = static_cast<ext_output_image_capture_source_manager_v1*>(
                        wl_registry_bind(r, name, &ext_output_image_capture_source_manager_v1_interface, 1));
                }
#endif
            },
            .global_remove = [](void*, wl_registry*, uint32_t) {},
        };
        wl_registry_add_listener(registry, &reg_l, &g);
        wl_display_roundtrip(g.display);
        wl_display_roundtrip(g.display);
        return true;
    }

    ~StandaloneWl() {
        for (auto& o : g.outputs) if (o.output) wl_output_destroy(o.output);
        if (g.cursor_mgr) wp_cursor_shape_manager_v1_destroy(g.cursor_mgr);
        if (g.frac_mgr) wp_fractional_scale_manager_v1_destroy(g.frac_mgr);
        if (g.viewporter) wp_viewporter_destroy(g.viewporter);
        if (g.layer_shell) zwlr_layer_shell_v1_destroy(g.layer_shell);
        if (g.wlr_screencopy_mgr) zwlr_screencopy_manager_v1_destroy(g.wlr_screencopy_mgr);
#if HSS_HAVE_EXT_IMAGE_COPY_CAPTURE
        if (g.ext_capture_mgr) ext_image_copy_capture_manager_v1_destroy(g.ext_capture_mgr);
        if (g.ext_source_mgr) ext_output_image_capture_source_manager_v1_destroy(g.ext_source_mgr);
#endif
        if (g.seat) wl_seat_destroy(g.seat);
        if (g.shm) wl_shm_destroy(g.shm);
        if (g.compositor) wl_compositor_destroy(g.compositor);
        if (registry) wl_registry_destroy(registry);
        if (g.display) wl_display_disconnect(g.display);
    }
};

uint32_t cursor_shape_for_handle(ResizeHandle h) {
    switch (h) {
        case ResizeHandle::NW: return WP_CURSOR_SHAPE_DEVICE_V1_SHAPE_NW_RESIZE;
        case ResizeHandle::NE: return WP_CURSOR_SHAPE_DEVICE_V1_SHAPE_NE_RESIZE;
        case ResizeHandle::SW: return WP_CURSOR_SHAPE_DEVICE_V1_SHAPE_SW_RESIZE;
        case ResizeHandle::SE: return WP_CURSOR_SHAPE_DEVICE_V1_SHAPE_SE_RESIZE;
        case ResizeHandle::N:  return WP_CURSOR_SHAPE_DEVICE_V1_SHAPE_N_RESIZE;
        case ResizeHandle::S:  return WP_CURSOR_SHAPE_DEVICE_V1_SHAPE_S_RESIZE;
        case ResizeHandle::W:  return WP_CURSOR_SHAPE_DEVICE_V1_SHAPE_W_RESIZE;
        case ResizeHandle::E:  return WP_CURSOR_SHAPE_DEVICE_V1_SHAPE_E_RESIZE;
        case ResizeHandle::Move: return WP_CURSOR_SHAPE_DEVICE_V1_SHAPE_GRAB;
        case ResizeHandle::None: return WP_CURSOR_SHAPE_DEVICE_V1_SHAPE_CROSSHAIR;
    }
    return WP_CURSOR_SHAPE_DEVICE_V1_SHAPE_CROSSHAIR;
}

}  // namespace

int OverlaySession::run(const CaptureRequest& req,
                        const nlohmann::json& cfg,
                        const I18n& i18n,
                        const std::string& self_exe,
                        WaylandSharedGlobals* shared_wl,
                        Clipboard* daemon_clipboard,
                        int daemon_srv_fd,
                        bool* daemon_quit_out) {
    auto t_start = std::chrono::steady_clock::now();

    std::unique_ptr<StandaloneWl> owned_wl;
    WaylandSharedGlobals* wl = shared_wl;
    if (!wl) {
        owned_wl = std::make_unique<StandaloneWl>();
        if (!owned_wl->connect()) {
            std::cerr << "Error: Failed to connect to Wayland display\n";
            return 1;
        }
        wl = &owned_wl->g;
    }

    // 1. Query focused monitor, active window class, and clients/layers over Hyprland UNIX socket (<1 ms)
    MonitorInfo monitor = HyprlandIpc::get_focused_monitor();
    WaylandOutput* target_out = nullptr;
    for (auto& o : wl->outputs) {
        if (!monitor.name.empty() && o.name == monitor.name) {
            target_out = &o;
            break;
        }
    }
    if (!target_out && !wl->outputs.empty()) target_out = &wl->outputs.front();
    if (!target_out) {
        std::cerr << "Error: No Wayland output found\n";
        return 1;
    }

    // 2. Capture raw BGRA frame directly into RAM via ext-image-copy-capture / wlr-screencopy
    ScreencopyHandles sh;
    sh.display = wl->display;
    sh.shm = wl->shm;
    sh.output = target_out->output;
    sh.output_transform = target_out->transform;
#if HSS_HAVE_EXT_IMAGE_COPY_CAPTURE
    sh.ext_capture_mgr = wl->ext_capture_mgr;
    sh.ext_source_mgr = wl->ext_source_mgr;
#endif
    sh.wlr_screencopy_mgr = wl->wlr_screencopy_mgr;

    auto captured = WaylandScreencopy::capture_output(sh);
    if (!captured || captured->empty()) {
        std::cerr << "Error: Screen capture failed\n";
        return 1;
    }

    // Fast 'full' bypass — zero overlay created
    if (req.mode == "full") {
        Actions::save_crop(*captured, cfg, i18n, true, daemon_clipboard);
        captured->data.clear();
        captured->data.shrink_to_fit();
        malloc_trim(0);
        return 0;
    }

    if (!wl->compositor || !wl->shm || !wl->layer_shell) {
        std::cerr << "Error: Compositor missing wlr-layer-shell support\n";
        return 1;
    }

    PixelBuffer freeze_img = std::move(*captured);
    ThemePalette pal = ConfigManager::resolve_palette(cfg);
    PixelBuffer dimmed_img = ImageOps::make_dimmed_copy(freeze_img, pal.dim_opacity);

    std::string active_class = HyprlandIpc::get_active_window_class();
    std::string preset_key = req.preset.empty() ? ConfigManager::resolve_preset_for_class(cfg, active_class) : req.preset;

    double init_scale = (monitor.scale > 0.0) ? monitor.scale : std::max(1, target_out->scale);
    int log_w = std::max(1, static_cast<int>(std::lround(freeze_img.width / init_scale)));
    int log_h = std::max(1, static_cast<int>(std::lround(freeze_img.height / init_scale)));

    struct SessionState {
        WaylandSharedGlobals* wl = nullptr;
        Clipboard* daemon_clipboard = nullptr;
        nlohmann::json cfg;
        ThemePalette pal;
        I18n i18n;
        std::string self_exe;
        PixelBuffer* freeze_img = nullptr;
        PixelBuffer* dimmed_img = nullptr;

        wl_surface* surface = nullptr;
        zwlr_layer_surface_v1* layer_surf = nullptr;
        wp_viewport* viewport = nullptr;
        wp_fractional_scale_v1* frac_scale = nullptr;
        wl_pointer* pointer = nullptr;
        wl_keyboard* keyboard = nullptr;
        wp_cursor_shape_device_v1* cursor_dev = nullptr;

        xkb_context* xkb_ctx = nullptr;
        xkb_keymap* xkb_map = nullptr;
        xkb_state* xkb_st = nullptr;

        SmartSelector selector;
        OverlayRenderer renderer;
        OverlayUiState ui;

        ShmBuffer shm_bufs[2];
        bool buf_busy[2] = {false, false};
        int cur_buf = 0;

        int logical_w = 1920;
        int logical_h = 1080;
        double scale = 1.0;
        uint32_t pointer_serial = 0;
        uint32_t last_cursor_shape = 0;

        bool configured = false;
        bool dirty = true;
        bool running = true;
        bool committed_once = false;

        std::chrono::steady_clock::time_point toast_expire{};
        VisionJob cv_job;
        VisionJob ai_job;
        std::vector<DetectedBox> latest_cv_boxes;

        enum class PendingAction { None, Copy, Save, Pin, Annotate, Ocr, AiOcr, AiDescribe, OpenSettings };
        PendingAction action = PendingAction::None;
        std::string settings_tab;

        void set_toast(const std::string& msg) {
            ui.status_toast = msg;
            toast_expire = std::chrono::steady_clock::now() + std::chrono::milliseconds(3000);
            dirty = true;
        }

        void update_cursor(uint32_t shape) {
            if (!cursor_dev || !pointer_serial || shape == last_cursor_shape) return;
            wp_cursor_shape_device_v1_set_shape(cursor_dev, pointer_serial, shape);
            last_cursor_shape = shape;
        }

        void trigger_action(PendingAction act) {
            if (act != PendingAction::OpenSettings && !selector.has_selection()) return;
            action = act;
            running = false;
        }

        void record_rating(bool liked, bool silent) {
            const CandidateBox* c = selector.selected_candidate();
            if (!c || (c->source != "cv" && c->source != "ai")) return;
            RatingEngine::record_feedback(c->type,
                                          static_cast<int>(std::lround(c->w)),
                                          static_cast<int>(std::lround(c->h)),
                                          liked, selector.active_preset(), cfg);
            if (!silent) {
                std::string prefix = liked ? ("+ " + i18n.t("ratePositive", "Boosted"))
                                           : ("− " + i18n.t("rateNegative", "Suppressed"));
                set_toast(prefix + " (" + c->type + ")");
            }
        }

        void start_ai_detection() {
            const auto ai_cfg = (cfg.contains("ai") && cfg["ai"].is_object()) ? cfg["ai"] : nlohmann::json::object();
            if (!ai_cfg.value("enabled", false)) {
                set_toast(i18n.t("aiDisabledTitle", "AI Vision Disabled") + " — " +
                          i18n.t("aiDisabledDesc", "Enable AI provider in Settings"));
                settings_tab = "ai";
                trigger_action(PendingAction::OpenSettings);
                return;
            }
            if (ui.ai_loading || ai_job.active()) return;
            ui.ai_loading = true;
            set_toast("AI detecting UI regions…");
            ai_job = VisionBridge::spawn_ai_boxes_job(*freeze_img, latest_cv_boxes, cfg, self_exe);
        }

        void redraw() {
            if (!surface || !wl->shm || logical_w <= 0 || logical_h <= 0) return;

            // Pick a free buffer slot (double-buffered wl_shm)
            int slot = !buf_busy[0] ? 0 : (!buf_busy[1] ? 1 : cur_buf);
            int phys_w = freeze_img->width;
            int phys_h = freeze_img->height;

            if (!shm_bufs[slot].valid() || shm_bufs[slot].width() != phys_w || shm_bufs[slot].height() != phys_h) {
                if (!shm_bufs[slot].allocate(wl->shm, phys_w, phys_h, WL_SHM_FORMAT_ARGB8888)) return;
                static const wl_buffer_listener buf_l = {
                    .release = [](void* data, wl_buffer*) { *static_cast<bool*>(data) = false; },
                };
                wl_buffer_add_listener(shm_bufs[slot].buffer(), &buf_l, &buf_busy[slot]);
            }

            double eff_scale = static_cast<double>(phys_w) / static_cast<double>(logical_w);
            renderer.render(shm_bufs[slot].data(), phys_w, phys_h, shm_bufs[slot].stride(),
                            eff_scale, *freeze_img, *dimmed_img, selector, ui, pal, cfg, i18n);

            if (viewport) {
                wp_viewport_set_destination(viewport, logical_w, logical_h);
            } else {
                wl_surface_set_buffer_scale(surface, std::max(1, static_cast<int>(std::lround(eff_scale))));
            }

            buf_busy[slot] = true;
            cur_buf = slot;
            wl_surface_attach(surface, shm_bufs[slot].buffer(), 0, 0);
            wl_surface_damage_buffer(surface, 0, 0, phys_w, phys_h);
            wl_surface_commit(surface);
            wl_display_flush(wl->display);
            dirty = false;
            committed_once = true;
        }
    } st;

    st.wl = wl;
    st.daemon_clipboard = daemon_clipboard;
    st.cfg = cfg;
    st.pal = pal;
    st.i18n = i18n;
    st.self_exe = self_exe;
    st.freeze_img = &freeze_img;
    st.dimmed_img = &dimmed_img;
    st.logical_w = log_w;
    st.logical_h = log_h;
    st.scale = init_scale;
    st.xkb_ctx = xkb_context_new(XKB_CONTEXT_NO_FLAGS);

    if (cfg.contains("ui") && cfg["ui"].is_object()) {
        st.ui.show_hints = cfg["ui"].value("showHints", true);
        st.ui.show_confidence = cfg["ui"].value("showConfidenceBadge", true);
        st.ui.magnifier_active = cfg["ui"].value("showMagnifierByDefault", false);
        st.ui.magnifier_zoom = cfg["ui"].value("magnifierZoom", 3.0);
        st.ui.magnifier_size = cfg["ui"].value("magnifierSize", 180.0);
    }
    st.ui.ocr_lang = cfg.value("ocrLanguages", std::string("eng"));
    if (st.ui.ocr_lang.empty()) st.ui.ocr_lang = "eng";

    st.selector.init(log_w, log_h, init_scale, req.mode, preset_key, cfg);

    // 3. Spawn COW-forked CV worker (0 persistent OpenCV/TBB RAM in parent, runs parallel to surface map!)
    if (!req.no_cv) {
        st.cv_job = VisionBridge::spawn_cv_job(freeze_img, monitor, preset_key, st.cfg, self_exe);
    }

    // Auto AI detection if forced or ai.trigger == "auto"
    bool run_ai_auto = (req.ai_force == 1);
    if (req.ai_force < 0 && cfg.contains("ai") && cfg["ai"].is_object()) {
        if (cfg["ai"].value("enabled", false) && cfg["ai"].value("trigger", std::string("manual")) == "auto") {
            run_ai_auto = true;
        }
    }

    // 4. Create Wayland overlay layer-shell surface
    st.surface = wl_compositor_create_surface(wl->compositor);
    if (wl->viewporter) st.viewport = wp_viewporter_get_viewport(wl->viewporter, st.surface);
    if (wl->frac_mgr) {
        st.frac_scale = wp_fractional_scale_manager_v1_get_fractional_scale(wl->frac_mgr, st.surface);
        static const wp_fractional_scale_v1_listener frac_l = {
            .preferred_scale = [](void* data, wp_fractional_scale_v1*, uint32_t s120) {
                auto* s = static_cast<SessionState*>(data);
                s->scale = std::max(0.5, s120 / 120.0);
                s->dirty = true;
            },
        };
        wp_fractional_scale_v1_add_listener(st.frac_scale, &frac_l, &st);
    }

    st.layer_surf = zwlr_layer_shell_v1_get_layer_surface(
        wl->layer_shell, st.surface, target_out->output,
        ZWLR_LAYER_SHELL_V1_LAYER_OVERLAY, "hyprsmartshot");
    zwlr_layer_surface_v1_set_anchor(st.layer_surf,
                                     ZWLR_LAYER_SURFACE_V1_ANCHOR_TOP | ZWLR_LAYER_SURFACE_V1_ANCHOR_BOTTOM |
                                     ZWLR_LAYER_SURFACE_V1_ANCHOR_LEFT | ZWLR_LAYER_SURFACE_V1_ANCHOR_RIGHT);
    zwlr_layer_surface_v1_set_exclusive_zone(st.layer_surf, -1);
    zwlr_layer_surface_v1_set_keyboard_interactivity(st.layer_surf,
                                                     ZWLR_LAYER_SURFACE_V1_KEYBOARD_INTERACTIVITY_EXCLUSIVE);

    static const zwlr_layer_surface_v1_listener layer_l = {
        .configure = [](void* data, zwlr_layer_surface_v1* ls, uint32_t serial, uint32_t w, uint32_t h) {
            auto* s = static_cast<SessionState*>(data);
            zwlr_layer_surface_v1_ack_configure(ls, serial);
            if (w > 0 && h > 0 && (static_cast<int>(w) != s->logical_w || static_cast<int>(h) != s->logical_h)) {
                s->logical_w = static_cast<int>(w);
                s->logical_h = static_cast<int>(h);
                double eff_scale = static_cast<double>(s->freeze_img->width) / static_cast<double>(s->logical_w);
                s->scale = eff_scale;
                s->selector.init(s->logical_w, s->logical_h, eff_scale, s->selector.mode(),
                                 s->selector.active_preset(), s->cfg);
                if (!s->latest_cv_boxes.empty()) {
                    s->selector.set_cv_boxes(s->latest_cv_boxes);
                }
            }
            s->configured = true;
            s->dirty = true;
        },
        .closed = [](void* data, zwlr_layer_surface_v1*) { static_cast<SessionState*>(data)->running = false; },
    };
    zwlr_layer_surface_v1_add_listener(st.layer_surf, &layer_l, &st);

    // Pointer & keyboard listeners (created per-session, destroyed on close!)
    static const wl_pointer_listener ptr_l = {
        .enter = [](void* data, wl_pointer*, uint32_t serial, wl_surface*, wl_fixed_t sx, wl_fixed_t sy) {
            auto* s = static_cast<SessionState*>(data);
            s->pointer_serial = serial;
            s->last_cursor_shape = 0;
            double x = wl_fixed_to_double(sx);
            double y = wl_fixed_to_double(sy);
            s->ui.hover_x = x;
            s->ui.hover_y = y;
            s->selector.on_pointer_move(x, y);
            s->update_cursor(WP_CURSOR_SHAPE_DEVICE_V1_SHAPE_CROSSHAIR);
            s->dirty = true;
        },
        .leave = [](void*, wl_pointer*, uint32_t, wl_surface*) {},
        .motion = [](void* data, wl_pointer*, uint32_t, wl_fixed_t sx, wl_fixed_t sy) {
            auto* s = static_cast<SessionState*>(data);
            double x = wl_fixed_to_double(sx);
            double y = wl_fixed_to_double(sy);
            s->ui.hover_x = x;
            s->ui.hover_y = y;
            if (!s->selector.is_dragging() && !s->selector.is_resizing() && s->renderer.point_in_chrome(x, y)) {
                s->update_cursor(WP_CURSOR_SHAPE_DEVICE_V1_SHAPE_POINTER);
            } else {
                s->selector.on_pointer_move(x, y);
                if (s->selector.is_confirmed() && !s->selector.is_dragging()) {
                    s->update_cursor(cursor_shape_for_handle(s->selector.hit_test_handle(x, y)));
                } else {
                    s->update_cursor(WP_CURSOR_SHAPE_DEVICE_V1_SHAPE_CROSSHAIR);
                }
            }
            s->dirty = true;
        },
        .button = [](void* data, wl_pointer*, uint32_t, uint32_t, uint32_t button, uint32_t state) {
            auto* s = static_cast<SessionState*>(data);
            if (button == BTN_RIGHT && state == WL_POINTER_BUTTON_STATE_PRESSED) {
                if (s->ui.preset_menu_open || s->ui.ocr_menu_open || s->ui.ai_menu_open) {
                    s->ui.preset_menu_open = s->ui.ocr_menu_open = s->ui.ai_menu_open = false;
                } else if (s->selector.is_confirmed()) {
                    s->selector.clear_confirmation();
                } else {
                    s->running = false;
                }
                s->dirty = true;
                return;
            }
            if (button != BTN_LEFT) return;

            double x = s->ui.hover_x, y = s->ui.hover_y;
            if (state == WL_POINTER_BUTTON_STATE_PRESSED) {
                auto hit = s->renderer.hit_test(x, y);
                if (hit.kind != UiHitKind::None) {
                    switch (hit.kind) {
                        case UiHitKind::ModeSmart:
                            s->selector.set_mode("universal");
                            break;
                        case UiHitKind::ModeScreen:
                            s->selector.set_mode("screen");
                            break;
                        case UiHitKind::PresetToggle:
                            s->ui.preset_menu_open = !s->ui.preset_menu_open;
                            s->ui.ocr_menu_open = s->ui.ai_menu_open = false;
                            break;
                        case UiHitKind::PresetOption:
                            s->selector.set_preset(hit.value);
                            s->ui.preset_menu_open = false;
                            break;
                        case UiHitKind::MagnifierToggle:
                            s->ui.magnifier_active = !s->ui.magnifier_active;
                            break;
                        case UiHitKind::AiDetect:
                            s->start_ai_detection();
                            break;
                        case UiHitKind::SettingsBtn:
                            s->trigger_action(SessionState::PendingAction::OpenSettings);
                            break;
                        case UiHitKind::CloseBtn:
                            s->running = false;
                            break;
                        case UiHitKind::ActionCopy:
                            s->trigger_action(SessionState::PendingAction::Copy);
                            break;
                        case UiHitKind::ActionSave:
                            s->trigger_action(SessionState::PendingAction::Save);
                            break;
                        case UiHitKind::ActionPin:
                            s->trigger_action(SessionState::PendingAction::Pin);
                            break;
                        case UiHitKind::ActionAnnotate:
                            s->trigger_action(SessionState::PendingAction::Annotate);
                            break;
                        case UiHitKind::ActionOcr:
                            s->trigger_action(SessionState::PendingAction::Ocr);
                            break;
                        case UiHitKind::ActionOcrMenu:
                            s->ui.ocr_menu_open = !s->ui.ocr_menu_open;
                            s->ui.ai_menu_open = s->ui.preset_menu_open = false;
                            break;
                        case UiHitKind::ActionOcrLang:
                            s->ui.ocr_lang = hit.value;
                            s->ui.ocr_menu_open = false;
                            break;
                        case UiHitKind::ActionAiMenu:
                            s->ui.ai_menu_open = !s->ui.ai_menu_open;
                            s->ui.ocr_menu_open = s->ui.preset_menu_open = false;
                            break;
                        case UiHitKind::ActionAiOcr:
                            s->trigger_action(SessionState::PendingAction::AiOcr);
                            break;
                        case UiHitKind::ActionAiDescribe:
                            s->trigger_action(SessionState::PendingAction::AiDescribe);
                            break;
                        case UiHitKind::ActionRateUp:
                            s->record_rating(true, false);
                            break;
                        case UiHitKind::ActionRateDown:
                            s->record_rating(false, false);
                            break;
                        case UiHitKind::ActionCancel:
                            s->selector.clear_confirmation();
                            break;
                        default:
                            break;
                    }
                    s->dirty = true;
                    return;
                }
                s->ui.preset_menu_open = s->ui.ocr_menu_open = s->ui.ai_menu_open = false;
                s->selector.on_pointer_press(x, y);
                s->dirty = true;
            } else if (state == WL_POINTER_BUTTON_STATE_RELEASED) {
                s->selector.on_pointer_release(x, y);
                s->dirty = true;
            }
        },
        .axis = [](void* data, wl_pointer*, uint32_t, uint32_t axis, wl_fixed_t value) {
            auto* s = static_cast<SessionState*>(data);
            if (axis != WL_POINTER_AXIS_VERTICAL_SCROLL) return;
            double v = wl_fixed_to_double(value);
            if (v != 0.0) {
                s->selector.on_wheel(v > 0 ? 1 : -1);
                s->dirty = true;
            }
        },
        .frame = [](void*, wl_pointer*) {},
        .axis_source = [](void*, wl_pointer*, uint32_t) {},
        .axis_stop = [](void*, wl_pointer*, uint32_t, uint32_t) {},
        .axis_discrete = [](void*, wl_pointer*, uint32_t, int32_t) {},
        .axis_value120 = [](void*, wl_pointer*, uint32_t, int32_t) {},
        .axis_relative_direction = [](void*, wl_pointer*, uint32_t, uint32_t) {},
    };

    static const wl_keyboard_listener kbd_l = {
        .keymap = [](void* data, wl_keyboard*, uint32_t format, int32_t fd, uint32_t size) {
            auto* s = static_cast<SessionState*>(data);
            if (format == WL_KEYBOARD_KEYMAP_FORMAT_XKB_V1 && s->xkb_ctx) {
                char* map = static_cast<char*>(::mmap(nullptr, size, PROT_READ, MAP_PRIVATE, fd, 0));
                if (map != MAP_FAILED) {
                    if (s->xkb_st) xkb_state_unref(s->xkb_st);
                    if (s->xkb_map) xkb_keymap_unref(s->xkb_map);
                    s->xkb_map = xkb_keymap_new_from_string(s->xkb_ctx, map, XKB_KEYMAP_FORMAT_TEXT_V1, XKB_KEYMAP_COMPILE_NO_FLAGS);
                    s->xkb_st = s->xkb_map ? xkb_state_new(s->xkb_map) : nullptr;
                    ::munmap(map, size);
                }
            }
            ::close(fd);
        },
        .enter = [](void*, wl_keyboard*, uint32_t, wl_surface*, wl_array*) {},
        .leave = [](void*, wl_keyboard*, uint32_t, wl_surface*) {},
        .key = [](void* data, wl_keyboard*, uint32_t, uint32_t, uint32_t key, uint32_t state) {
            auto* s = static_cast<SessionState*>(data);
            if (state != WL_KEYBOARD_KEY_STATE_PRESSED || !s->xkb_st) return;
            xkb_keysym_t sym = xkb_state_key_get_one_sym(s->xkb_st, key + 8);
            bool ctrl = xkb_state_mod_name_is_active(s->xkb_st, XKB_MOD_NAME_CTRL, XKB_STATE_MODS_EFFECTIVE) > 0;
            bool shift = xkb_state_mod_name_is_active(s->xkb_st, XKB_MOD_NAME_SHIFT, XKB_STATE_MODS_EFFECTIVE) > 0;
            bool alt = xkb_state_mod_name_is_active(s->xkb_st, XKB_MOD_NAME_ALT, XKB_STATE_MODS_EFFECTIVE) > 0;

            if (sym == XKB_KEY_Escape) {
                if (s->ui.preset_menu_open || s->ui.ocr_menu_open || s->ui.ai_menu_open) {
                    s->ui.preset_menu_open = s->ui.ocr_menu_open = s->ui.ai_menu_open = false;
                } else if (s->selector.is_confirmed()) {
                    s->selector.clear_confirmation();
                } else {
                    s->running = false;
                }
            } else if (sym == XKB_KEY_Return || sym == XKB_KEY_KP_Enter || sym == XKB_KEY_space) {
                s->trigger_action(SessionState::PendingAction::Copy);
            } else if ((ctrl && (sym == XKB_KEY_q || sym == XKB_KEY_Q)) ||
                       (!s->selector.is_confirmed() && (sym == XKB_KEY_q || sym == XKB_KEY_Q))) {
                s->running = false;
            } else if ((ctrl && (sym == XKB_KEY_c || sym == XKB_KEY_C)) ||
                       (s->selector.is_confirmed() && (sym == XKB_KEY_c || sym == XKB_KEY_C))) {
                s->trigger_action(SessionState::PendingAction::Copy);
            } else if ((ctrl && (sym == XKB_KEY_s || sym == XKB_KEY_S)) ||
                       (s->selector.is_confirmed() && (sym == XKB_KEY_s || sym == XKB_KEY_S))) {
                s->trigger_action(SessionState::PendingAction::Save);
            } else if (sym == XKB_KEY_p || sym == XKB_KEY_P) {
                s->trigger_action(SessionState::PendingAction::Pin);
            } else if (sym == XKB_KEY_a || sym == XKB_KEY_A || sym == XKB_KEY_e || sym == XKB_KEY_E) {
                s->trigger_action(SessionState::PendingAction::Annotate);
            } else if (sym == XKB_KEY_o || sym == XKB_KEY_O) {
                s->trigger_action(SessionState::PendingAction::Ocr);
            } else if (sym == XKB_KEY_i || sym == XKB_KEY_I) {
                s->start_ai_detection();
            } else if (sym == XKB_KEY_comma) {
                s->trigger_action(SessionState::PendingAction::OpenSettings);
            } else if (sym == XKB_KEY_Alt_L || sym == XKB_KEY_Alt_R) {
                s->ui.magnifier_active = !s->ui.magnifier_active;
            } else if (sym == XKB_KEY_Tab) {
                s->selector.cycle_hierarchy(shift ? -1 : 1);
            } else if (sym == XKB_KEY_1) {
                s->selector.set_mode("universal");
            } else if (sym == XKB_KEY_2) {
                s->selector.set_mode("screen");
            } else if (s->selector.is_confirmed() && (sym == XKB_KEY_plus || sym == XKB_KEY_equal)) {
                s->record_rating(true, false);
            } else if (s->selector.is_confirmed() && sym == XKB_KEY_minus) {
                s->record_rating(false, false);
            } else if (sym == XKB_KEY_Left || sym == XKB_KEY_Right || sym == XKB_KEY_Up || sym == XKB_KEY_Down) {
                double step = shift ? 10.0 : 1.0;
                if (s->selector.is_confirmed()) {
                    if (alt) {
                        if (sym == XKB_KEY_Left) s->selector.resize(-step, 0);
                        else if (sym == XKB_KEY_Right) s->selector.resize(step, 0);
                        else if (sym == XKB_KEY_Up) s->selector.resize(0, -step);
                        else if (sym == XKB_KEY_Down) s->selector.resize(0, step);
                    } else {
                        if (sym == XKB_KEY_Left) s->selector.nudge(-step, 0);
                        else if (sym == XKB_KEY_Right) s->selector.nudge(step, 0);
                        else if (sym == XKB_KEY_Up) s->selector.nudge(0, -step);
                        else if (sym == XKB_KEY_Down) s->selector.nudge(0, step);
                    }
                } else {
                    if (sym == XKB_KEY_Up) s->selector.cycle_hierarchy(1);
                    else if (sym == XKB_KEY_Down) s->selector.cycle_hierarchy(-1);
                }
            }
            s->dirty = true;
        },
        .modifiers = [](void* data, wl_keyboard*, uint32_t, uint32_t dep, uint32_t lat, uint32_t lck, uint32_t grp) {
            auto* s = static_cast<SessionState*>(data);
            if (s->xkb_st) xkb_state_update_mask(s->xkb_st, dep, lat, lck, 0, 0, grp);
        },
        .repeat_info = [](void*, wl_keyboard*, int32_t, int32_t) {},
    };

    if (wl->seat) {
        st.pointer = wl_seat_get_pointer(wl->seat);
        if (st.pointer) {
            wl_pointer_add_listener(st.pointer, &ptr_l, &st);
            if (wl->cursor_mgr) {
                st.cursor_dev = wp_cursor_shape_manager_v1_get_pointer(wl->cursor_mgr, st.pointer);
            }
        }
        st.keyboard = wl_seat_get_keyboard(wl->seat);
        if (st.keyboard) wl_keyboard_add_listener(st.keyboard, &kbd_l, &st);
    }

    wl_surface_commit(st.surface);
    wl_display_flush(wl->display);

    if (run_ai_auto) st.start_ai_detection();

    // 5. Main single-threaded poll loop (Wayland events + CV/AI child pipes + toast expiry)
    int wl_fd = wl_display_get_fd(wl->display);
    while (st.running) {
        while (wl_display_prepare_read(wl->display) != 0) {
            wl_display_dispatch_pending(wl->display);
        }
        wl_display_flush(wl->display);

        if (!st.ui.status_toast.empty() && std::chrono::steady_clock::now() >= st.toast_expire) {
            st.ui.status_toast.clear();
            st.dirty = true;
        }

        if (st.configured && st.dirty) {
            wl_display_cancel_read(wl->display);
            st.redraw();
            if (req.benchmark_exit && st.committed_once) {
                auto dt = std::chrono::duration<double, std::milli>(
                              std::chrono::steady_clock::now() - t_start)
                              .count();
                std::cout << "benchmark_first_commit_ms=" << dt << "\n";
                st.running = false;
            }
            continue;
        }

        pollfd pfds[4];
        pfds[0] = {wl_fd, POLLIN, 0};
        pfds[1] = {st.cv_job.active() ? st.cv_job.read_fd : -1, POLLIN, 0};
        pfds[2] = {st.ai_job.active() ? st.ai_job.read_fd : -1, POLLIN, 0};
        pfds[3] = {daemon_srv_fd, POLLIN, 0};
        int timeout_ms = st.ui.status_toast.empty() ? 250 : 100;
        int pr = ::poll(pfds, 4, timeout_ms);
        if (pr > 0 && (pfds[0].revents & POLLIN)) {
            wl_display_read_events(wl->display);
            wl_display_dispatch_pending(wl->display);
        } else {
            wl_display_cancel_read(wl->display);
        }
        if (pr > 0 && pfds[1].fd >= 0 && (pfds[1].revents & (POLLIN | POLLHUP | POLLERR))) {
            if (st.cv_job.poll_read_done()) {
                st.latest_cv_boxes = VisionBridge::parse_boxes_json(st.cv_job.buffer);
                st.cv_job.buffer.clear();
                st.selector.set_cv_boxes(st.latest_cv_boxes);
                st.dirty = true;
            }
        }
        if (pr > 0 && pfds[2].fd >= 0 && (pfds[2].revents & (POLLIN | POLLHUP | POLLERR))) {
            if (st.ai_job.poll_read_done()) {
                st.ui.ai_loading = false;
                std::string err;
                auto ai_boxes = VisionBridge::parse_boxes_json(st.ai_job.buffer, &err);
                st.ai_job.buffer.clear();
                if (err.empty()) {
                    st.selector.set_ai_boxes(ai_boxes);
                    st.set_toast("AI: " + std::to_string(ai_boxes.size()) + " regions");
                } else {
                    st.set_toast("AI error: " + err.substr(0, 64));
                }
                st.dirty = true;
            }
        }
        if (pr > 0 && pfds[3].fd >= 0 && (pfds[3].revents & POLLIN)) {
            int cfd = ::accept4(daemon_srv_fd, nullptr, nullptr, SOCK_CLOEXEC);
            if (cfd >= 0) {
                ucred cred{};
                socklen_t clen = sizeof(cred);
                if (::getsockopt(cfd, SOL_SOCKET, SO_PEERCRED, &cred, &clen) == 0 && cred.uid == geteuid()) {
                    char rbuf[1024];
                    pollfd cpfd{cfd, POLLIN, 0};
                    std::string raw;
                    if (::poll(&cpfd, 1, 200) > 0) {
                        ssize_t n = ::recv(cfd, rbuf, sizeof(rbuf), 0);
                        if (n > 0) raw.append(rbuf, static_cast<size_t>(n));
                    }
                    try {
                        auto msg = nlohmann::json::parse(raw);
                        std::string cmd = msg.value("cmd", std::string());
                        if (cmd == "quit") {
                            if (daemon_quit_out) *daemon_quit_out = true;
                            st.running = false;
                            const char* ok = "{\"ok\":true}\n";
                            (void)::send(cfd, ok, std::strlen(ok), MSG_NOSIGNAL);
                        } else if (cmd == "capture" || cmd == "cancel") {
                            // Re-pressing hotkey cleanly toggles/dismisses active overlay
                            st.running = false;
                            const char* ok = "{\"ok\":true,\"toggled_off\":true}\n";
                            (void)::send(cfd, ok, std::strlen(ok), MSG_NOSIGNAL);
                        } else if (cmd == "reload-config") {
                            st.cfg = ConfigManager::load_config(req.explicit_config);
                            st.pal = ConfigManager::resolve_palette(st.cfg);
                            st.dirty = true;
                            const char* ok = "{\"ok\":true}\n";
                            (void)::send(cfd, ok, std::strlen(ok), MSG_NOSIGNAL);
                        } else if (cmd == "ping" || cmd == "status") {
                            const char* ok = "{\"ok\":true,\"active\":true}\n";
                            (void)::send(cfd, ok, std::strlen(ok), MSG_NOSIGNAL);
                        }
                    } catch (...) {}
                }
                ::close(cfd);
            }
        }
    }

    // Cancel any in-flight CV/AI child instantaneously (never blocks close!)
    st.cv_job.cancel();
    st.ai_job.cancel();

    // 6. Immediately hide & destroy overlay Wayland objects BEFORE running slow I/O actions
    // so screen unfreezes instantaneously!
    st.shm_bufs[0].release();
    st.shm_bufs[1].release();
    if (st.cursor_dev) wp_cursor_shape_device_v1_destroy(st.cursor_dev);
    if (st.pointer) wl_pointer_destroy(st.pointer);
    if (st.keyboard) wl_keyboard_destroy(st.keyboard);
    if (st.frac_scale) wp_fractional_scale_v1_destroy(st.frac_scale);
    if (st.viewport) wp_viewport_destroy(st.viewport);
    if (st.layer_surf) zwlr_layer_surface_v1_destroy(st.layer_surf);
    if (st.surface) wl_surface_destroy(st.surface);
    if (st.xkb_st) xkb_state_unref(st.xkb_st);
    if (st.xkb_map) xkb_keymap_unref(st.xkb_map);
    if (st.xkb_ctx) xkb_context_unref(st.xkb_ctx);
    wl_display_flush(wl->display);
    wl_display_roundtrip(wl->display);

    // Free dimmed backdrop immediately
    dimmed_img.data.clear();
    dimmed_img.data.shrink_to_fit();

    // 7. Execute selected action on in-RAM crop (zero magick, zero /tmp freeze PNG!)
    if (st.action != SessionState::PendingAction::None) {
        if (st.action == SessionState::PendingAction::OpenSettings) {
            Actions::launch_settings_gui(self_exe, st.settings_tab);
        } else {
            double eff_scale = static_cast<double>(freeze_img.width) / static_cast<double>(st.logical_w);
            RectI crop_r = ImageOps::compute_physical_crop(
                st.selector.sel_x(), st.selector.sel_y(),
                st.selector.sel_w(), st.selector.sel_h(),
                eff_scale, freeze_img.width, freeze_img.height);
            PixelBuffer cropped = ImageOps::crop(freeze_img, crop_r);

            if (st.action == SessionState::PendingAction::Copy) {
                st.record_rating(true, true);
                Actions::copy_crop(cropped, cfg, i18n, daemon_clipboard);
            } else if (st.action == SessionState::PendingAction::Save) {
                st.record_rating(true, true);
                Actions::save_crop(cropped, cfg, i18n, false, daemon_clipboard);
            } else if (st.action == SessionState::PendingAction::Pin) {
                st.record_rating(true, true);
                Actions::pin_crop(cropped,
                                  static_cast<int>(std::lround(st.selector.sel_x())),
                                  static_cast<int>(std::lround(st.selector.sel_y())),
                                  static_cast<int>(std::lround(st.selector.sel_w())),
                                  static_cast<int>(std::lround(st.selector.sel_h())),
                                  pal, i18n, self_exe);
            } else if (st.action == SessionState::PendingAction::Annotate) {
                st.record_rating(true, true);
                Actions::annotate_crop(cropped, cfg, i18n);
            } else if (st.action == SessionState::PendingAction::Ocr) {
                Actions::ocr_crop(cropped, st.ui.ocr_lang, cfg, i18n, daemon_clipboard);
            } else if (st.action == SessionState::PendingAction::AiOcr) {
                Actions::ai_vision_crop(cropped, "ocr", cfg, i18n, daemon_clipboard);
            } else if (st.action == SessionState::PendingAction::AiDescribe) {
                Actions::ai_vision_crop(cropped, "describe", cfg, i18n, daemon_clipboard);
            }
        }
    }

    // 8. Reclaim heap pages back to OS -> keeps idle daemon RSS < 10 MB!
    freeze_img.data.clear();
    freeze_img.data.shrink_to_fit();
    malloc_trim(0);
    return 0;
}

}  // namespace hss
