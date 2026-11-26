#pragma once

#include "core/hyprland_ipc.hpp"
#include "core/image_ops.hpp"
#include "vision/rating.hpp"

#include <string>
#include <sys/types.h>
#include <vector>

#include <nlohmann/json.hpp>

namespace hss {

struct VisionJob {
    pid_t pid = -1;
    int read_fd = -1;
    std::string buffer;

    bool active() const { return read_fd >= 0; }
    void cancel();
    // Non-blocking drain; returns true once EOF reached (and reaps child)
    bool poll_read_done();
};

struct VisionAiStatus {
    bool enabled = false;
    bool reachable = false;
    std::string provider;
    std::string model;
    std::string trigger;
    std::string detail;
};

struct VisionAiActionOut {
    bool ok = false;
    std::string text;
    std::string error;
};

class VisionBridge {
public:
    static std::string resolve_plugin_path(const std::string& self_exe = "");

    // Spawn COW-forked child that dlopens libhss_vision.so, runs OpenCV + Hyprland clients/layers,
    // writes boxes JSON to pipe, and exits (0 persistent OpenCV/TBB RAM in parent daemon!)
    static VisionJob spawn_cv_job(const PixelBuffer& freeze_img,
                                  const MonitorInfo& monitor,
                                  const std::string& preset_key,
                                  const nlohmann::json& cfg,
                                  const std::string& self_exe = "");

    static VisionJob spawn_ai_boxes_job(const PixelBuffer& freeze_img,
                                        const std::vector<DetectedBox>& cv_boxes,
                                        const nlohmann::json& cfg,
                                        const std::string& self_exe = "");

    static VisionAiActionOut run_ai_action_forked(const PixelBuffer& cropped,
                                                  const std::string& action_mode,
                                                  const nlohmann::json& cfg,
                                                  const std::string& self_exe = "");

    static VisionAiStatus check_ai_status_forked(const nlohmann::json& cfg,
                                                 const std::string& self_exe = "");

    static std::vector<DetectedBox> parse_boxes_json(const std::string& raw_json,
                                                     std::string* error_out = nullptr,
                                                     double* elapsed_ms_out = nullptr);
};

}  // namespace hss
