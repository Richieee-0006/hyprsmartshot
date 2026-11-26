#include "wayland/pin_window.hpp"
#include "core/actions.hpp"
#include "core/hyprland_ipc.hpp"
#include "core/image_ops.hpp"
#include "wayland/clipboard.hpp"
#include "wayland/shm.hpp"

#include <algorithm>
#include <cairo/cairo.h>
#include <chrono>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <linux/input-event-codes.h>
#include <sys/mman.h>
#include <unistd.h>
#include <wayland-client.h>
#include <xkbcommon/xkbcommon.h>

#include "cursor-shape-v1-client-protocol.h"
#include "fractional-scale-v1-client-protocol.h"
#include "viewporter-client-protocol.h"
#include "xdg-shell-client-protocol.h"

namespace hss {

namespace fs = std::filesystem;

bool PinWindow::is_temporary_path(const std::string& path) {
    if (path.empty()) return false;
    std::error_code ec;
    fs::path canon = fs::weakly_canonical(path, ec);
    std::string s = ec ? path : canon.string();
    if (s.rfind("/tmp/", 0) == 0 || s.rfind("/var/tmp/", 0) == 0) return true;
    std::string base = fs::path(path).filename().string();
    return base.rfind("hyprsmartshot", 0) == 0;
}

int PinWindow::run(const PinOptions& opts, const nlohmann::json& cfg) {
    if (opts.image_path.empty()) {
        std::cerr << "Error: Missing image path for 'pin'\n";
        return 1;
    }
    std::error_code ec;
    if (!fs::is_regular_file(opts.image_path, ec)) {
        std::cerr << "Error: Image not found: " << opts.image_path << "\n";
        return 1;
    }

    auto img_opt = ImageOps::load_image(opts.image_path);
    if (!img_opt || img_opt->empty()) {
        std::cerr << "Error: Failed to load image: " << opts.image_path << "\n";
        return 1;
    }
    PixelBuffer img = std::move(*img_opt);

    // Zero temp file accumulation: delete temporary screenshot immediately after reading into RAM
    bool should_delete = opts.delete_source.has_value() ? *opts.delete_source : is_temporary_path(opts.image_path);
    if (should_delete) {
        fs::remove(opts.image_path, ec);
    }

    ThemePalette pal = ConfigManager::resolve_palette(cfg);
    Color bg_col = opts.bg_color.empty() ? pal.card_background : Color::from_hex(opts.bg_color, 1.0);
    Color border_col = opts.border_color.empty() ? pal.pin_border : Color::from_hex(opts.border_color, 0.85);
    int border_w = (opts.border_width >= 0)
                       ? std::clamp(opts.border_width, 0, 8)
                       : std::clamp(static_cast<int>(std::lround(pal.pin_border_width)), 1, 8);

    wl_display* display = wl_display_connect(nullptr);
    if (!display) {
        std::cerr << "Error: Failed to connect to Wayland display\n";
        return 1;
    }

    struct State {
        wl_display* display = nullptr;
        wl_compositor* compositor = nullptr;
        wl_shm* shm = nullptr;
        wl_seat* seat = nullptr;
        wl_pointer* pointer = nullptr;
        wl_keyboard* keyboard = nullptr;
        xdg_wm_base* wm_base = nullptr;
        wp_viewporter* viewporter = nullptr;
        wp_fractional_scale_manager_v1* frac_mgr = nullptr;
        wp_cursor_shape_manager_v1* cursor_mgr = nullptr;
        wp_cursor_shape_device_v1* cursor_dev = nullptr;

        wl_surface* surface = nullptr;
        xdg_surface* xdg_surf = nullptr;
        xdg_toplevel* toplevel = nullptr;
        wp_viewport* viewport = nullptr;
        wp_fractional_scale_v1* frac_scale = nullptr;

        xkb_context* xkb_ctx = nullptr;
        xkb_keymap* xkb_map = nullptr;
        xkb_state* xkb_st = nullptr;

        PixelBuffer* img = nullptr;
        Color bg;
        Color border;
        int border_w = 2;

        double base_w = 100.0;
        double base_h = 100.0;
        double zoom = 1.0;
        int cur_w = 100;
        int cur_h = 100;
        double scale = 1.0;

        bool configured = false;
        bool dirty = true;
        bool running = true;
        bool hypr_positioned = false;
        std::optional<int> target_x;
        std::optional<int> target_y;
        uint32_t last_click_ms = 0;
        ShmBuffer shm_buf;

        void redraw() {
            if (!surface || !shm || cur_w <= 0 || cur_h <= 0) return;
            int phys_w = std::max(1, static_cast<int>(std::lround(cur_w * scale)));
            int phys_h = std::max(1, static_cast<int>(std::lround(cur_h * scale)));

            if (!shm_buf.valid() || shm_buf.width() != phys_w || shm_buf.height() != phys_h) {
                if (!shm_buf.allocate(shm, phys_w, phys_h, WL_SHM_FORMAT_ARGB8888)) return;
            }

            cairo_surface_t* dst = cairo_image_surface_create_for_data(
                shm_buf.data(), CAIRO_FORMAT_ARGB32, phys_w, phys_h, shm_buf.stride());
            cairo_t* cr = cairo_create(dst);

            cairo_set_source_rgba(cr, bg.r, bg.g, bg.b, 1.0);
            cairo_paint(cr);

            int pad = static_cast<int>(std::lround(border_w * scale));
            int inner_w = std::max(1, phys_w - pad * 2);
            int inner_h = std::max(1, phys_h - pad * 2);

            cairo_surface_t* src_surf = cairo_image_surface_create_for_data(
                img->data.data(), CAIRO_FORMAT_RGB24, img->width, img->height, img->stride);
            cairo_save(cr);
            cairo_translate(cr, pad, pad);
            cairo_scale(cr, static_cast<double>(inner_w) / img->width,
                        static_cast<double>(inner_h) / img->height);
            cairo_set_source_surface(cr, src_surf, 0, 0);
            cairo_pattern_set_filter(cairo_get_source(cr), CAIRO_FILTER_BILINEAR);
            cairo_paint(cr);
            cairo_restore(cr);
            cairo_surface_destroy(src_surf);

            if (pad > 0) {
                cairo_set_source_rgba(cr, border.r, border.g, border.b, border.a);
                cairo_set_line_width(cr, pad);
                cairo_rectangle(cr, pad * 0.5, pad * 0.5, phys_w - pad, phys_h - pad);
                cairo_stroke(cr);
            }

            cairo_destroy(cr);
            cairo_surface_destroy(dst);

            if (viewport) {
                wp_viewport_set_destination(viewport, cur_w, cur_h);
            } else {
                wl_surface_set_buffer_scale(surface, std::max(1, static_cast<int>(std::lround(scale))));
            }
            wl_surface_attach(surface, shm_buf.buffer(), 0, 0);
            wl_surface_damage_buffer(surface, 0, 0, phys_w, phys_h);
            wl_surface_commit(surface);
            wl_display_flush(display);
            dirty = false;
        }

        void apply_zoom(double new_zoom) {
            zoom = std::clamp(new_zoom, 0.2, 6.0);
            cur_w = std::max(48, static_cast<int>(std::lround(base_w * zoom)));
            cur_h = std::max(48, static_cast<int>(std::lround(base_h * zoom)));
            dirty = true;
        }

        void copy_to_clipboard() {
            auto png = ImageOps::encode_png(*img, 0);
            if (!png.empty()) Clipboard::copy_via_wl_copy(png, "image/png");
        }
    } st;

    st.display = display;
    st.img = &img;
    st.bg = bg_col;
    st.border = border_col;
    st.border_w = border_w;
    st.base_w = (opts.width && *opts.width > 20) ? *opts.width : img.width;
    st.base_h = (opts.height && *opts.height > 20) ? *opts.height : img.height;
    st.target_x = opts.x;
    st.target_y = opts.y;
    st.cur_w = static_cast<int>(std::lround(st.base_w));
    st.cur_h = static_cast<int>(std::lround(st.base_h));
    st.xkb_ctx = xkb_context_new(XKB_CONTEXT_NO_FLAGS);

    static const xdg_wm_base_listener wm_base_listener = {
        .ping = [](void*, xdg_wm_base* base, uint32_t serial) { xdg_wm_base_pong(base, serial); },
    };

    static const wl_pointer_listener ptr_listener = {
        .enter = [](void* data, wl_pointer*, uint32_t serial, wl_surface*, wl_fixed_t, wl_fixed_t) {
            auto* s = static_cast<State*>(data);
            if (s->cursor_dev) {
                wp_cursor_shape_device_v1_set_shape(s->cursor_dev, serial, WP_CURSOR_SHAPE_DEVICE_V1_SHAPE_GRAB);
            }
        },
        .leave = [](void*, wl_pointer*, uint32_t, wl_surface*) {},
        .motion = [](void*, wl_pointer*, uint32_t, wl_fixed_t, wl_fixed_t) {},
        .button = [](void* data, wl_pointer*, uint32_t serial, uint32_t time_ms,
                     uint32_t button, uint32_t state) {
            auto* s = static_cast<State*>(data);
            if (state != WL_POINTER_BUTTON_STATE_PRESSED) return;
            if (button == BTN_RIGHT || button == BTN_MIDDLE) {
                s->running = false;
                return;
            }
            if (button == BTN_LEFT) {
                if (time_ms - s->last_click_ms < 320) {
                    s->apply_zoom(1.0);
                    s->last_click_ms = 0;
                    return;
                }
                s->last_click_ms = time_ms;
                if (s->toplevel && s->seat) {
                    xdg_toplevel_move(s->toplevel, s->seat, serial);
                }
            }
        },
        .axis = [](void* data, wl_pointer*, uint32_t, uint32_t axis, wl_fixed_t value) {
            auto* s = static_cast<State*>(data);
            if (axis != WL_POINTER_AXIS_VERTICAL_SCROLL) return;
            double v = wl_fixed_to_double(value);
            if (v < 0) s->apply_zoom(s->zoom * 1.12);
            else if (v > 0) s->apply_zoom(s->zoom / 1.12);
        },
        .frame = [](void*, wl_pointer*) {},
        .axis_source = [](void*, wl_pointer*, uint32_t) {},
        .axis_stop = [](void*, wl_pointer*, uint32_t, uint32_t) {},
        .axis_discrete = [](void*, wl_pointer*, uint32_t, int32_t) {},
        .axis_value120 = [](void*, wl_pointer*, uint32_t, int32_t) {},
        .axis_relative_direction = [](void*, wl_pointer*, uint32_t, uint32_t) {},
    };

    static const wl_keyboard_listener kbd_listener = {
        .keymap = [](void* data, wl_keyboard*, uint32_t format, int32_t fd, uint32_t size) {
            auto* s = static_cast<State*>(data);
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
            auto* s = static_cast<State*>(data);
            if (state != WL_KEYBOARD_KEY_STATE_PRESSED || !s->xkb_st) return;
            xkb_keysym_t sym = xkb_state_key_get_one_sym(s->xkb_st, key + 8);
            bool ctrl = xkb_state_mod_name_is_active(s->xkb_st, XKB_MOD_NAME_CTRL, XKB_STATE_MODS_EFFECTIVE) > 0;
            if (sym == XKB_KEY_Escape || sym == XKB_KEY_q || sym == XKB_KEY_Q) {
                s->running = false;
            } else if ((ctrl && (sym == XKB_KEY_c || sym == XKB_KEY_C)) || sym == XKB_KEY_Return || sym == XKB_KEY_KP_Enter) {
                s->copy_to_clipboard();
            } else if (sym == XKB_KEY_plus || sym == XKB_KEY_equal || sym == XKB_KEY_KP_Add) {
                s->apply_zoom(s->zoom * 1.15);
            } else if (sym == XKB_KEY_minus || sym == XKB_KEY_KP_Subtract) {
                s->apply_zoom(s->zoom / 1.15);
            } else if (sym == XKB_KEY_0 || sym == XKB_KEY_KP_0) {
                s->apply_zoom(1.0);
            }
        },
        .modifiers = [](void* data, wl_keyboard*, uint32_t, uint32_t dep, uint32_t lat, uint32_t lck, uint32_t grp) {
            auto* s = static_cast<State*>(data);
            if (s->xkb_st) xkb_state_update_mask(s->xkb_st, dep, lat, lck, 0, 0, grp);
        },
        .repeat_info = [](void*, wl_keyboard*, int32_t, int32_t) {},
    };

    static const wl_seat_listener seat_listener = {
        .capabilities = [](void* data, wl_seat* seat, uint32_t caps) {
            auto* s = static_cast<State*>(data);
            if ((caps & WL_SEAT_CAPABILITY_POINTER) && !s->pointer) {
                s->pointer = wl_seat_get_pointer(seat);
                wl_pointer_add_listener(s->pointer, &ptr_listener, s);
                if (s->cursor_mgr) {
                    s->cursor_dev = wp_cursor_shape_manager_v1_get_pointer(s->cursor_mgr, s->pointer);
                }
            }
            if ((caps & WL_SEAT_CAPABILITY_KEYBOARD) && !s->keyboard) {
                s->keyboard = wl_seat_get_keyboard(seat);
                wl_keyboard_add_listener(s->keyboard, &kbd_listener, s);
            }
        },
        .name = [](void*, wl_seat*, const char*) {},
    };

    wl_registry* reg = wl_display_get_registry(display);
    static const wl_registry_listener reg_listener = {
        .global = [](void* data, wl_registry* r, uint32_t name, const char* iface, uint32_t ver) {
            auto* s = static_cast<State*>(data);
            if (std::strcmp(iface, wl_compositor_interface.name) == 0) {
                s->compositor = static_cast<wl_compositor*>(wl_registry_bind(r, name, &wl_compositor_interface, std::min(ver, 5u)));
            } else if (std::strcmp(iface, wl_shm_interface.name) == 0) {
                s->shm = static_cast<wl_shm*>(wl_registry_bind(r, name, &wl_shm_interface, 1));
            } else if (std::strcmp(iface, wl_seat_interface.name) == 0) {
                s->seat = static_cast<wl_seat*>(wl_registry_bind(r, name, &wl_seat_interface, std::min(ver, 7u)));
                wl_seat_add_listener(s->seat, &seat_listener, s);
            } else if (std::strcmp(iface, xdg_wm_base_interface.name) == 0) {
                s->wm_base = static_cast<xdg_wm_base*>(wl_registry_bind(r, name, &xdg_wm_base_interface, std::min(ver, 4u)));
                xdg_wm_base_add_listener(s->wm_base, &wm_base_listener, s);
            } else if (std::strcmp(iface, wp_viewporter_interface.name) == 0) {
                s->viewporter = static_cast<wp_viewporter*>(wl_registry_bind(r, name, &wp_viewporter_interface, 1));
            } else if (std::strcmp(iface, wp_fractional_scale_manager_v1_interface.name) == 0) {
                s->frac_mgr = static_cast<wp_fractional_scale_manager_v1*>(
                    wl_registry_bind(r, name, &wp_fractional_scale_manager_v1_interface, 1));
            } else if (std::strcmp(iface, wp_cursor_shape_manager_v1_interface.name) == 0) {
                s->cursor_mgr = static_cast<wp_cursor_shape_manager_v1*>(
                    wl_registry_bind(r, name, &wp_cursor_shape_manager_v1_interface, 1));
            }
        },
        .global_remove = [](void*, wl_registry*, uint32_t) {},
    };
    wl_registry_add_listener(reg, &reg_listener, &st);
    wl_display_roundtrip(display);
    wl_display_roundtrip(display);

    if (!st.compositor || !st.shm || !st.wm_base) {
        wl_registry_destroy(reg);
        wl_display_disconnect(display);
        return 1;
    }

    st.surface = wl_compositor_create_surface(st.compositor);
    if (st.viewporter) st.viewport = wp_viewporter_get_viewport(st.viewporter, st.surface);
    if (st.frac_mgr) {
        st.frac_scale = wp_fractional_scale_manager_v1_get_fractional_scale(st.frac_mgr, st.surface);
        static const wp_fractional_scale_v1_listener frac_listener = {
            .preferred_scale = [](void* data, wp_fractional_scale_v1*, uint32_t scale120) {
                auto* s = static_cast<State*>(data);
                s->scale = std::max(0.5, scale120 / 120.0);
                s->dirty = true;
            },
        };
        wp_fractional_scale_v1_add_listener(st.frac_scale, &frac_listener, &st);
    }

    st.xdg_surf = xdg_wm_base_get_xdg_surface(st.wm_base, st.surface);
    static const xdg_surface_listener xdg_surf_listener = {
        .configure = [](void* data, xdg_surface* xs, uint32_t serial) {
            auto* s = static_cast<State*>(data);
            xdg_surface_ack_configure(xs, serial);
            s->configured = true;
            s->dirty = true;
        },
    };
    xdg_surface_add_listener(st.xdg_surf, &xdg_surf_listener, &st);

    st.toplevel = xdg_surface_get_toplevel(st.xdg_surf);
    xdg_toplevel_set_app_id(st.toplevel, "hyprsmartshot-pin");
    xdg_toplevel_set_title(st.toplevel, "HyprSmartShot Pin");

    static const xdg_toplevel_listener toplevel_listener = {
        .configure = [](void* data, xdg_toplevel*, int32_t w, int32_t h, wl_array*) {
            auto* s = static_cast<State*>(data);
            if (w > 0 && h > 0) {
                double aspect = s->base_w / std::max(1.0, s->base_h);
                int nw = w;
                int nh = std::max(32, static_cast<int>(std::lround(nw / aspect)));
                if (nh > h) {
                    nh = h;
                    nw = std::max(32, static_cast<int>(std::lround(nh * aspect)));
                }
                s->cur_w = nw;
                s->cur_h = nh;
                s->zoom = nw / std::max(1.0, s->base_w);
                s->dirty = true;
            }
        },
        .close = [](void* data, xdg_toplevel*) { static_cast<State*>(data)->running = false; },
        .configure_bounds = [](void*, xdg_toplevel*, int32_t, int32_t) {},
        .wm_capabilities = [](void*, xdg_toplevel*, wl_array*) {},
    };
    xdg_toplevel_add_listener(st.toplevel, &toplevel_listener, &st);

    wl_surface_commit(st.surface);
    wl_display_flush(display);

    static const wl_callback_listener map_frame_listener = {
        .done = [](void* data, wl_callback* cb, uint32_t) {
            wl_callback_destroy(cb);
            auto* s = static_cast<State*>(data);
            if (!s->hypr_positioned && HyprlandIpc::available()) {
                s->hypr_positioned = true;
                std::string sel = "pid:" + std::to_string(getpid());
                HyprlandIpc::dispatch("setfloating " + sel);
                if (s->target_x && s->target_y) {
                    HyprlandIpc::dispatch("movewindowpixel exact " + std::to_string(*s->target_x) + " " +
                                          std::to_string(*s->target_y) + "," + sel);
                }
                HyprlandIpc::dispatch("pin " + sel);
            }
        },
    };

    bool frame_cb_armed = false;
    while (st.running && wl_display_dispatch(display) != -1) {
        if (st.configured && st.dirty) {
            if (!frame_cb_armed && HyprlandIpc::available()) {
                frame_cb_armed = true;
                wl_callback* cb = wl_surface_frame(st.surface);
                wl_callback_add_listener(cb, &map_frame_listener, &st);
            }
            st.redraw();
        }
    }

    st.shm_buf.release();
    if (st.cursor_dev) wp_cursor_shape_device_v1_destroy(st.cursor_dev);
    if (st.cursor_mgr) wp_cursor_shape_manager_v1_destroy(st.cursor_mgr);
    if (st.frac_scale) wp_fractional_scale_v1_destroy(st.frac_scale);
    if (st.frac_mgr) wp_fractional_scale_manager_v1_destroy(st.frac_mgr);
    if (st.viewport) wp_viewport_destroy(st.viewport);
    if (st.viewporter) wp_viewporter_destroy(st.viewporter);
    if (st.toplevel) xdg_toplevel_destroy(st.toplevel);
    if (st.xdg_surf) xdg_surface_destroy(st.xdg_surf);
    if (st.surface) wl_surface_destroy(st.surface);
    if (st.pointer) wl_pointer_destroy(st.pointer);
    if (st.keyboard) wl_keyboard_destroy(st.keyboard);
    if (st.seat) wl_seat_destroy(st.seat);
    if (st.wm_base) xdg_wm_base_destroy(st.wm_base);
    if (st.shm) wl_shm_destroy(st.shm);
    if (st.compositor) wl_compositor_destroy(st.compositor);
    if (st.xkb_st) xkb_state_unref(st.xkb_st);
    if (st.xkb_map) xkb_keymap_unref(st.xkb_map);
    if (st.xkb_ctx) xkb_context_unref(st.xkb_ctx);
    wl_registry_destroy(reg);
    wl_display_disconnect(display);
    return 0;
}

}  // namespace hss
