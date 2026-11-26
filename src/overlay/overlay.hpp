#pragma once

#include "core/config.hpp"
#include "core/hyprland_ipc.hpp"
#include "core/i18n.hpp"
#include "wayland/clipboard.hpp"
#include "wayland/screencopy.hpp"

#include <string>
#include <vector>
#include <wayland-client.h>

struct zwlr_layer_shell_v1;
struct wp_viewporter;
struct wp_fractional_scale_manager_v1;
struct wp_cursor_shape_manager_v1;

namespace hss {

struct CaptureRequest {
    std::string mode = "universal";  // "universal" | "screen" | "window" | "full"
    std::string preset;
    std::string explicit_config;
    int ai_force = -1;               // -1 auto, 0 disable, 1 force
    bool no_cv = false;
    bool benchmark_exit = false;     // internal: exit right after first surface commit for latency testing
};

struct WaylandSharedGlobals {
    wl_display* display = nullptr;
    wl_compositor* compositor = nullptr;
    wl_shm* shm = nullptr;
    wl_seat* seat = nullptr;
    zwlr_layer_shell_v1* layer_shell = nullptr;
    zwlr_screencopy_manager_v1* wlr_screencopy_mgr = nullptr;
#if HSS_HAVE_EXT_IMAGE_COPY_CAPTURE
    ext_image_copy_capture_manager_v1* ext_capture_mgr = nullptr;
    ext_output_image_capture_source_manager_v1* ext_source_mgr = nullptr;
#endif
    wp_viewporter* viewporter = nullptr;
    wp_fractional_scale_manager_v1* frac_mgr = nullptr;
    wp_cursor_shape_manager_v1* cursor_mgr = nullptr;
    std::vector<WaylandOutput> outputs;
};

class OverlaySession {
public:
    // Run a complete capture session (either using daemon's pre-connected Wayland globals or standalone).
    // Guaranteed to destroy all overlay surfaces, buffers, and call malloc_trim(0) before returning.
    static int run(const CaptureRequest& req,
                   const nlohmann::json& cfg,
                   const I18n& i18n,
                   const std::string& self_exe,
                   WaylandSharedGlobals* shared_wl = nullptr,
                   Clipboard* daemon_clipboard = nullptr,
                   int daemon_srv_fd = -1,
                   bool* daemon_quit_out = nullptr);
};

}  // namespace hss
