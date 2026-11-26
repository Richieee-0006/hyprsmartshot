#include "wayland/screencopy.hpp"
#include "wayland/shm.hpp"

#include <algorithm>
#include <cstring>
#include <drm/drm_fourcc.h>

#include "wlr-screencopy-unstable-v1-client-protocol.h"
#if HSS_HAVE_EXT_IMAGE_COPY_CAPTURE
#include "ext-image-capture-source-v1-client-protocol.h"
#include "ext-image-copy-capture-v1-client-protocol.h"
#endif

namespace hss {

PixelBuffer WaylandScreencopy::normalize_buffer(const uint8_t* src, int width, int height,
                                                int stride, uint32_t wl_format, bool y_invert) {
    PixelBuffer out;
    if (!src || width <= 0 || height <= 0 || stride < width * 4) return out;

    out.width = width;
    out.height = height;
    out.stride = width * 4;
    out.data.resize(static_cast<size_t>(out.stride) * static_cast<size_t>(height));

    const bool is_bgra = (wl_format == WL_SHM_FORMAT_ARGB8888 || wl_format == WL_SHM_FORMAT_XRGB8888);
    const bool is_rgba = (wl_format == WL_SHM_FORMAT_ABGR8888 || wl_format == WL_SHM_FORMAT_XBGR8888);
    const bool is_xbgr210 = (wl_format == WL_SHM_FORMAT_XBGR2101010 || wl_format == WL_SHM_FORMAT_ABGR2101010);
    const bool is_xrgb210 = (wl_format == WL_SHM_FORMAT_XRGB2101010 || wl_format == WL_SHM_FORMAT_ARGB2101010);

    for (int y = 0; y < height; ++y) {
        int sy = y_invert ? (height - 1 - y) : y;
        const uint8_t* sr = src + static_cast<size_t>(sy) * stride;
        uint8_t* dr = out.data.data() + static_cast<size_t>(y) * out.stride;

        if (is_bgra) {
            std::memcpy(dr, sr, static_cast<size_t>(width) * 4);
            for (int x = 0; x < width; ++x) dr[x * 4 + 3] = 255;
        } else if (is_rgba) {
            for (int x = 0; x < width; ++x) {
                dr[x * 4 + 0] = sr[x * 4 + 2];  // B
                dr[x * 4 + 1] = sr[x * 4 + 1];  // G
                dr[x * 4 + 2] = sr[x * 4 + 0];  // R
                dr[x * 4 + 3] = 255;
            }
        } else if (is_xbgr210 || is_xrgb210) {
            const auto* p32 = reinterpret_cast<const uint32_t*>(sr);
            for (int x = 0; x < width; ++x) {
                uint32_t v = p32[x];
                uint8_t c0 = static_cast<uint8_t>((v & 0x3FFu) >> 2);
                uint8_t c1 = static_cast<uint8_t>(((v >> 10) & 0x3FFu) >> 2);
                uint8_t c2 = static_cast<uint8_t>(((v >> 20) & 0x3FFu) >> 2);
                if (is_xbgr210) {
                    dr[x * 4 + 0] = c2;  // B
                    dr[x * 4 + 1] = c1;  // G
                    dr[x * 4 + 2] = c0;  // R
                } else {
                    dr[x * 4 + 0] = c0;  // B
                    dr[x * 4 + 1] = c1;  // G
                    dr[x * 4 + 2] = c2;  // R
                }
                dr[x * 4 + 3] = 255;
            }
        } else {
            // Fallback copy assuming BGRA-like 32bpp
            std::memcpy(dr, sr, static_cast<size_t>(width) * 4);
            for (int x = 0; x < width; ++x) dr[x * 4 + 3] = 255;
        }
    }
    return out;
}

namespace {

#if HSS_HAVE_EXT_IMAGE_COPY_CAPTURE
uint32_t pick_ext_shm_format(const std::vector<uint32_t>& fmts) {
    for (uint32_t pref : {
             static_cast<uint32_t>(WL_SHM_FORMAT_XRGB8888),
             static_cast<uint32_t>(WL_SHM_FORMAT_ARGB8888),
             static_cast<uint32_t>(WL_SHM_FORMAT_XBGR8888),
             static_cast<uint32_t>(WL_SHM_FORMAT_ABGR8888),
             static_cast<uint32_t>(WL_SHM_FORMAT_XRGB2101010),
             static_cast<uint32_t>(WL_SHM_FORMAT_XBGR2101010),
         }) {
        if (std::find(fmts.begin(), fmts.end(), pref) != fmts.end()) return pref;
    }
    return fmts.empty() ? static_cast<uint32_t>(WL_SHM_FORMAT_XRGB8888) : fmts.front();
}

std::optional<PixelBuffer> capture_via_ext(const ScreencopyHandles& h) {
    if (!h.ext_capture_mgr || !h.ext_source_mgr || !h.output || !h.shm || !h.display) {
        return std::nullopt;
    }

    struct ExtState {
        int width = 0;
        int height = 0;
        std::vector<uint32_t> shm_formats;
        bool constraints_done = false;
        bool stopped = false;
        bool frame_ready = false;
        bool frame_failed = false;
        uint32_t transform = WL_OUTPUT_TRANSFORM_NORMAL;
    } st;

    ext_image_capture_source_v1* source =
        ext_output_image_capture_source_manager_v1_create_source(h.ext_source_mgr, h.output);
    if (!source) return std::nullopt;

    ext_image_copy_capture_session_v1* session =
        ext_image_copy_capture_manager_v1_create_session(h.ext_capture_mgr, source, 0);
    if (!session) {
        ext_image_capture_source_v1_destroy(source);
        return std::nullopt;
    }

    static const ext_image_copy_capture_session_v1_listener session_listener = {
        .buffer_size = [](void* data, ext_image_copy_capture_session_v1*, uint32_t w, uint32_t h) {
            auto* s = static_cast<ExtState*>(data);
            s->width = static_cast<int>(w);
            s->height = static_cast<int>(h);
        },
        .shm_format = [](void* data, ext_image_copy_capture_session_v1*, uint32_t fmt) {
            static_cast<ExtState*>(data)->shm_formats.push_back(fmt);
        },
        .dmabuf_device = [](void*, ext_image_copy_capture_session_v1*, wl_array*) {},
        .dmabuf_format = [](void*, ext_image_copy_capture_session_v1*, uint32_t, wl_array*) {},
        .done = [](void* data, ext_image_copy_capture_session_v1*) {
            static_cast<ExtState*>(data)->constraints_done = true;
        },
        .stopped = [](void* data, ext_image_copy_capture_session_v1*) {
            static_cast<ExtState*>(data)->stopped = true;
        },
    };
    ext_image_copy_capture_session_v1_add_listener(session, &session_listener, &st);

    while (!st.constraints_done && !st.stopped) {
        if (wl_display_dispatch(h.display) < 0) break;
    }

    if (st.stopped || st.width <= 0 || st.height <= 0 || st.shm_formats.empty()) {
        ext_image_copy_capture_session_v1_destroy(session);
        ext_image_capture_source_v1_destroy(source);
        return std::nullopt;
    }

    uint32_t fmt = pick_ext_shm_format(st.shm_formats);
    ShmBuffer shm_buf;
    if (!shm_buf.allocate(h.shm, st.width, st.height, fmt)) {
        ext_image_copy_capture_session_v1_destroy(session);
        ext_image_capture_source_v1_destroy(source);
        return std::nullopt;
    }

    ext_image_copy_capture_frame_v1* frame = ext_image_copy_capture_session_v1_create_frame(session);
    static const ext_image_copy_capture_frame_v1_listener frame_listener = {
        .transform = [](void* data, ext_image_copy_capture_frame_v1*, uint32_t tr) {
            static_cast<ExtState*>(data)->transform = tr;
        },
        .damage = [](void*, ext_image_copy_capture_frame_v1*, int32_t, int32_t, int32_t, int32_t) {},
        .presentation_time = [](void*, ext_image_copy_capture_frame_v1*, uint32_t, uint32_t, uint32_t) {},
        .ready = [](void* data, ext_image_copy_capture_frame_v1*) {
            static_cast<ExtState*>(data)->frame_ready = true;
        },
        .failed = [](void* data, ext_image_copy_capture_frame_v1*, uint32_t) {
            static_cast<ExtState*>(data)->frame_failed = true;
        },
    };
    ext_image_copy_capture_frame_v1_add_listener(frame, &frame_listener, &st);
    ext_image_copy_capture_frame_v1_attach_buffer(frame, shm_buf.buffer());
    ext_image_copy_capture_frame_v1_damage_buffer(frame, 0, 0, st.width, st.height);
    ext_image_copy_capture_frame_v1_capture(frame);
    wl_display_flush(h.display);

    while (!st.frame_ready && !st.frame_failed && !st.stopped) {
        if (wl_display_dispatch(h.display) < 0) break;
    }

    std::optional<PixelBuffer> result;
    if (st.frame_ready) {
        bool y_inv = (st.transform == WL_OUTPUT_TRANSFORM_FLIPPED_180);
        result = WaylandScreencopy::normalize_buffer(
            shm_buf.data(), st.width, st.height, shm_buf.stride(), fmt, y_inv);
    }

    ext_image_copy_capture_frame_v1_destroy(frame);
    ext_image_copy_capture_session_v1_destroy(session);
    ext_image_capture_source_v1_destroy(source);
    wl_display_flush(h.display);
    return result;
}
#endif

std::optional<PixelBuffer> capture_via_wlr(const ScreencopyHandles& h) {
    if (!h.wlr_screencopy_mgr || !h.output || !h.shm || !h.display) {
        return std::nullopt;
    }

    struct WlrState {
        uint32_t format = WL_SHM_FORMAT_XRGB8888;
        int width = 0;
        int height = 0;
        int stride = 0;
        uint32_t flags = 0;
        bool buffer_info = false;
        bool ready = false;
        bool failed = false;
    } st;

    zwlr_screencopy_frame_v1* frame =
        zwlr_screencopy_manager_v1_capture_output(h.wlr_screencopy_mgr, 0, h.output);
    if (!frame) return std::nullopt;

    static const zwlr_screencopy_frame_v1_listener listener = {
        .buffer = [](void* data, zwlr_screencopy_frame_v1*, uint32_t fmt,
                     uint32_t w, uint32_t h, uint32_t stride) {
            auto* s = static_cast<WlrState*>(data);
            s->format = fmt;
            s->width = static_cast<int>(w);
            s->height = static_cast<int>(h);
            s->stride = static_cast<int>(stride);
            s->buffer_info = true;
        },
        .flags = [](void* data, zwlr_screencopy_frame_v1*, uint32_t flags) {
            static_cast<WlrState*>(data)->flags = flags;
        },
        .ready = [](void* data, zwlr_screencopy_frame_v1*, uint32_t, uint32_t, uint32_t) {
            static_cast<WlrState*>(data)->ready = true;
        },
        .failed = [](void* data, zwlr_screencopy_frame_v1*) {
            static_cast<WlrState*>(data)->failed = true;
        },
        .damage = [](void*, zwlr_screencopy_frame_v1*, uint32_t, uint32_t, uint32_t, uint32_t) {},
        .linux_dmabuf = [](void*, zwlr_screencopy_frame_v1*, uint32_t, uint32_t, uint32_t) {},
        .buffer_done = [](void*, zwlr_screencopy_frame_v1*) {},
    };
    zwlr_screencopy_frame_v1_add_listener(frame, &listener, &st);

    while (!st.buffer_info && !st.failed) {
        if (wl_display_dispatch(h.display) < 0) break;
    }

    if (st.failed || !st.buffer_info || st.width <= 0 || st.height <= 0) {
        zwlr_screencopy_frame_v1_destroy(frame);
        return std::nullopt;
    }

    ShmBuffer shm_buf;
    if (!shm_buf.allocate(h.shm, st.width, st.height, st.format, st.stride)) {
        zwlr_screencopy_frame_v1_destroy(frame);
        return std::nullopt;
    }

    zwlr_screencopy_frame_v1_copy(frame, shm_buf.buffer());
    wl_display_flush(h.display);

    while (!st.ready && !st.failed) {
        if (wl_display_dispatch(h.display) < 0) break;
    }

    std::optional<PixelBuffer> result;
    if (st.ready) {
        bool y_inv = (st.flags & ZWLR_SCREENCOPY_FRAME_V1_FLAGS_Y_INVERT) != 0;
        result = WaylandScreencopy::normalize_buffer(
            shm_buf.data(), st.width, st.height, shm_buf.stride(), st.format, y_inv);
    }

    zwlr_screencopy_frame_v1_destroy(frame);
    wl_display_flush(h.display);
    return result;
}

}  // namespace

std::optional<PixelBuffer> WaylandScreencopy::capture_output(const ScreencopyHandles& h) {
#if HSS_HAVE_EXT_IMAGE_COPY_CAPTURE
    if (h.ext_capture_mgr && h.ext_source_mgr) {
        if (auto res = capture_via_ext(h)) return res;
    }
#endif
    if (h.wlr_screencopy_mgr) {
        return capture_via_wlr(h);
    }
    return std::nullopt;
}

std::optional<PixelBuffer> WaylandScreencopy::capture_standalone(const std::string& monitor_name) {
    wl_display* display = wl_display_connect(nullptr);
    if (!display) return std::nullopt;

    struct StandaloneCtx {
        wl_shm* shm = nullptr;
        zwlr_screencopy_manager_v1* wlr_mgr = nullptr;
#if HSS_HAVE_EXT_IMAGE_COPY_CAPTURE
        ext_image_copy_capture_manager_v1* ext_cap = nullptr;
        ext_output_image_capture_source_manager_v1* ext_src = nullptr;
#endif
        std::vector<WaylandOutput> outputs;
    } ctx;

    static const wl_output_listener out_listener = {
        .geometry = [](void* data, wl_output*, int32_t x, int32_t y, int32_t, int32_t,
                       int32_t, const char*, const char*, int32_t transform) {
            auto* o = static_cast<WaylandOutput*>(data);
            o->x = x;
            o->y = y;
            o->transform = transform;
        },
        .mode = [](void* data, wl_output*, uint32_t flags, int32_t w, int32_t h, int32_t) {
            if (flags & WL_OUTPUT_MODE_CURRENT) {
                auto* o = static_cast<WaylandOutput*>(data);
                o->width = w;
                o->height = h;
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

    ctx.outputs.reserve(16);
    wl_registry* reg = wl_display_get_registry(display);
    static const wl_registry_listener reg_listener = {
        .global = [](void* data, wl_registry* r, uint32_t name, const char* iface, uint32_t ver) {
            auto* c = static_cast<StandaloneCtx*>(data);
            if (std::strcmp(iface, wl_shm_interface.name) == 0) {
                c->shm = static_cast<wl_shm*>(wl_registry_bind(r, name, &wl_shm_interface, 1));
            } else if (std::strcmp(iface, wl_output_interface.name) == 0) {
                if (c->outputs.size() < 16) {
                    WaylandOutput wo;
                    wo.global_name = name;
                    wo.output = static_cast<wl_output*>(
                        wl_registry_bind(r, name, &wl_output_interface, std::min(ver, 4u)));
                    c->outputs.push_back(wo);
                    wl_output_add_listener(c->outputs.back().output, &out_listener, &c->outputs.back());
                }
            } else if (std::strcmp(iface, zwlr_screencopy_manager_v1_interface.name) == 0) {
                c->wlr_mgr = static_cast<zwlr_screencopy_manager_v1*>(
                    wl_registry_bind(r, name, &zwlr_screencopy_manager_v1_interface, std::min(ver, 3u)));
            }
#if HSS_HAVE_EXT_IMAGE_COPY_CAPTURE
            else if (std::strcmp(iface, ext_image_copy_capture_manager_v1_interface.name) == 0) {
                c->ext_cap = static_cast<ext_image_copy_capture_manager_v1*>(
                    wl_registry_bind(r, name, &ext_image_copy_capture_manager_v1_interface, 1));
            } else if (std::strcmp(iface, ext_output_image_capture_source_manager_v1_interface.name) == 0) {
                c->ext_src = static_cast<ext_output_image_capture_source_manager_v1*>(
                    wl_registry_bind(r, name, &ext_output_image_capture_source_manager_v1_interface, 1));
            }
#endif
        },
        .global_remove = [](void*, wl_registry*, uint32_t) {},
    };
    wl_registry_add_listener(reg, &reg_listener, &ctx);
    wl_display_roundtrip(display);
    wl_display_roundtrip(display);

    WaylandOutput* target = nullptr;
    for (auto& o : ctx.outputs) {
        if (!monitor_name.empty() && o.name == monitor_name) {
            target = &o;
            break;
        }
    }
    if (!target && !ctx.outputs.empty()) target = &ctx.outputs.front();

    std::optional<PixelBuffer> result;
    if (target) {
        ScreencopyHandles sh;
        sh.display = display;
        sh.shm = ctx.shm;
        sh.output = target->output;
        sh.output_transform = target->transform;
#if HSS_HAVE_EXT_IMAGE_COPY_CAPTURE
        sh.ext_capture_mgr = ctx.ext_cap;
        sh.ext_source_mgr = ctx.ext_src;
#endif
        sh.wlr_screencopy_mgr = ctx.wlr_mgr;
        result = capture_output(sh);
    }

    for (auto& o : ctx.outputs) {
        if (o.output) wl_output_destroy(o.output);
    }
#if HSS_HAVE_EXT_IMAGE_COPY_CAPTURE
    if (ctx.ext_cap) ext_image_copy_capture_manager_v1_destroy(ctx.ext_cap);
    if (ctx.ext_src) ext_output_image_capture_source_manager_v1_destroy(ctx.ext_src);
#endif
    if (ctx.wlr_mgr) zwlr_screencopy_manager_v1_destroy(ctx.wlr_mgr);
    if (ctx.shm) wl_shm_destroy(ctx.shm);
    wl_registry_destroy(reg);
    wl_display_disconnect(display);
    return result;
}

}  // namespace hss
