#pragma once

#include "core/hyprland_ipc.hpp"
#include "core/image_ops.hpp"
#include "vision/rating.hpp"

#include <filesystem>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace hss {

struct CvDetectionOptions {
    int monitor_x = 0;
    int monitor_y = 0;
    double monitor_scale = 1.0;
    int active_workspace_id = 0;
    std::string preset_key = "default";
    std::filesystem::path explicit_rating_profile;
};

struct CvDetectionResult {
    int screen_width = 0;
    int screen_height = 0;
    std::string preset;
    double elapsed_ms = 0.0;
    std::vector<DetectedBox> boxes;
};

class CvDetector {
public:
    static CvDetectionResult detect(const PixelBuffer& img,
                                    const std::vector<ClientWindow>& clients,
                                    const nlohmann::json& cfg,
                                    const CvDetectionOptions& opts = {});

    // Pure algorithmic helpers exposed for unit testing
    static std::vector<DetectedBox> deduplicate_boxes(const std::vector<DetectedBox>& boxes,
                                                      double iou_thresh = 0.72,
                                                      double contain_thresh = 0.88);
    static std::vector<DetectedBox> cluster_slots_and_grids(std::vector<DetectedBox>& boxes);
    static std::vector<DetectedBox> cluster_adjacent_columns(const std::vector<DetectedBox>& boxes);
    static std::vector<DetectedBox> cluster_text_paragraphs(const std::vector<DetectedBox>& text_lines,
                                                            int min_lines = 2,
                                                            bool multi_column = true);
};

}  // namespace hss
