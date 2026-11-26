#pragma once

#include "core/image_ops.hpp"
#include "vision/rating.hpp"

#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace hss {

struct AiBoxesResult {
    bool ok = false;
    std::string error;
    std::vector<DetectedBox> boxes;
};

struct AiActionResult {
    bool ok = false;
    std::string text;
    std::string error;
};

struct AiStatus {
    bool enabled = false;
    bool reachable = false;
    std::string provider;
    std::string model;
    std::string trigger;
    std::string detail;
};

class AiClient {
public:
    static std::pair<std::string, nlohmann::json> resolve_provider(const nlohmann::json& cfg,
                                                                   const std::string& override_provider = "");
    static AiBoxesResult detect_boxes(const PixelBuffer& img,
                                      const nlohmann::json& cfg,
                                      const std::vector<DetectedBox>& cv_boxes = {},
                                      const std::string& custom_prompt = "");
    static AiActionResult run_vision_action(const PixelBuffer& cropped,
                                            const std::string& action_mode,
                                            const nlohmann::json& cfg);
    static AiStatus check_status(const nlohmann::json& cfg);

    static std::vector<std::string> list_provider_models(const nlohmann::json& cfg,
                                                         const std::string& provider_override = "",
                                                         bool force_refresh = false);

    // Pure helpers exposed for unit testing
    static std::vector<DetectedBox> extract_ai_boxes(const std::string& raw_text,
                                                     int crop_w, int crop_h,
                                                     int offset_x = 0, int offset_y = 0);
    static void snap_to_cv(std::vector<DetectedBox>& ai_boxes,
                           const std::vector<DetectedBox>& cv_boxes,
                           int tol = 24);
};

}  // namespace hss
