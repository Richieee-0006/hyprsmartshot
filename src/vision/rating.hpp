#pragma once

#include <filesystem>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

#include <nlohmann/json.hpp>

namespace hss {

struct DetectedBox {
    int id = 0;
    int x = 0;
    int y = 0;
    int w = 0;
    int h = 0;
    int area = 0;
    double extent = 1.0;
    double contrast = 30.0;
    std::optional<double> edge_score;
    std::optional<double> interior_edge;
    std::string type = "detected";
    std::string label;
    std::string title;
    std::string wm_class;
    std::string source = "cv";  // "cv" | "ai" | "client"
    std::string rating_source = "heuristic";
    bool is_client = false;
    bool floating = false;
    bool pinned = false;
    bool is_layer = false;
    int focus_history_id = 999;
    double confidence = 0.80;
    double ai_confidence = 0.88;
    int score = 80;
    int depth = 0;

    nlohmann::json to_json() const;
};

struct RatingProfile {
    int version = 1;
    int samples = 0;
    std::unordered_map<std::string, double> biases;
};

class RatingEngine {
public:
    static std::filesystem::path resolve_profile_path(const nlohmann::json& rating_cfg);
    static RatingProfile load_profile(const std::filesystem::path& path);
    static bool save_profile(const RatingProfile& profile, const std::filesystem::path& path);

    static std::string size_bucket(int w, int h);
    static std::string profile_key(const std::string& box_type, int w, int h, const std::string& preset_key);

    static RatingProfile record_feedback(const std::string& box_type,
                                         int w, int h,
                                         bool liked,
                                         const std::string& preset_key,
                                         const nlohmann::json& cfg,
                                         const std::filesystem::path& explicit_profile = {});

    static std::pair<double, int> score_box(const DetectedBox& box,
                                            const std::string& active_preset,
                                            const nlohmann::json& rating_cfg,
                                            const RatingProfile* profile = nullptr);

    static std::vector<DetectedBox> rate_and_filter(const std::vector<DetectedBox>& boxes,
                                                    const std::string& active_preset,
                                                    const nlohmann::json& cfg,
                                                    const std::filesystem::path& explicit_profile = {});
};

}  // namespace hss
