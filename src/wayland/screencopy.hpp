#pragma once

#include "core/image_ops.hpp"

#include <cstdint>
#include <optional>
#include <string>
#include <vector>
#include <wayland-client.h>

#if HSS_HAVE_EXT_IMAGE_COPY_CAPTURE
struct ext_image_copy_capture_manager_v1;
struct ext_output_image_capture_source_manager_v1;
#endif
struct zwlr_screencopy_manager_v1;

namespace hss {

struct WaylandOutput {
    wl_output* output = nullptr;
    uint32_t global_name = 0;
    std::string name;
    int32_t x = 0;
    int32_t y = 0;
    int32_t width = 0;
    int32_t height = 0;
    int32_t scale = 1;
    int32_t transform = WL_OUTPUT_TRANSFORM_NORMAL;
};

struct ScreencopyHandles {
    wl_display* display = nullptr;
    wl_shm* shm = nullptr;
    wl_output* output = nullptr;
    int32_t output_transform = WL_OUTPUT_TRANSFORM_NORMAL;
#if HSS_HAVE_EXT_IMAGE_COPY_CAPTURE
    ext_image_copy_capture_manager_v1* ext_capture_mgr = nullptr;
    ext_output_image_capture_source_manager_v1* ext_source_mgr = nullptr;
#endif
    zwlr_screencopy_manager_v1* wlr_screencopy_mgr = nullptr;
};

class WaylandScreencopy {
public:
    // Capture using an existing Wayland connection (daemon fast path)
    static std::optional<PixelBuffer> capture_output(const ScreencopyHandles& h);

    // Standalone one-shot capture opening its own Wayland connection
    static std::optional<PixelBuffer> capture_standalone(const std::string& monitor_name);

    // Convert arbitrary captured SHM format + y_invert into canonical top-left BGRA8888
    static PixelBuffer normalize_buffer(const uint8_t* src, int width, int height,
                                        int stride, uint32_t wl_format, bool y_invert);
};

}  // namespace hss
