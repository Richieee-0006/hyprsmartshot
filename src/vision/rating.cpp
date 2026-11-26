#include "vision/rating.hpp"
#include "core/config.hpp"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <unistd.h>

namespace hss {

namespace fs = std::filesystem;

namespace {

const std::unordered_map<std::string, double> kBaseTypeScore = {
    {"floating_window", 0.96}, {"window", 0.94}, {"ai", 0.92},
    {"grid_container", 0.88}, {"grid_row", 0.84}, {"panel", 0.84},
    {"content", 0.84}, {"input", 0.82}, {"button", 0.78},
    {"slot", 0.76}, {"item", 0.74}, {"text_block", 0.75},
    {"text", 0.72}, {"detected", 0.62},
};

double preset_type_fit(const std::string& preset, const std::string& b_type) {
    static const std::unordered_map<std::string, std::unordered_map<std::string, double>> kTable = {
        {"default", {
            {"window", 0.92}, {"floating_window", 0.95}, {"panel", 0.90}, {"content", 0.88},
            {"input", 0.86}, {"button", 0.82}, {"text_block", 0.82}, {"text", 0.78},
            {"slot", 0.72}, {"item", 0.68}, {"grid_row", 0.76}, {"grid_container", 0.80},
            {"detected", 0.60}, {"ai", 0.95},
        }},
        {"browser", {
            {"panel", 0.95}, {"content", 0.96}, {"input", 0.92}, {"button", 0.88},
            {"text_block", 0.88}, {"text", 0.82}, {"window", 0.86}, {"floating_window", 0.88},
            {"detected", 0.74}, {"slot", 0.35}, {"item", 0.30}, {"grid_row", 0.35},
            {"grid_container", 0.40}, {"ai", 0.95},
        }},
        {"terminal", {
            {"window", 0.96}, {"floating_window", 0.95}, {"panel", 0.92}, {"content", 0.90},
            {"text_block", 0.92}, {"text", 0.88}, {"input", 0.86}, {"detected", 0.45},
            {"button", 0.35}, {"slot", 0.25}, {"item", 0.20}, {"grid_row", 0.25},
            {"grid_container", 0.25}, {"ai", 0.94},
        }},
        {"game", {
            {"slot", 0.96}, {"item", 0.92}, {"grid_row", 0.95}, {"grid_container", 0.96},
            {"panel", 0.90}, {"button", 0.86}, {"input", 0.78}, {"detected", 0.76},
            {"window", 0.84}, {"floating_window", 0.86}, {"text_block", 0.42}, {"text", 0.35},
            {"ai", 0.96},
        }},
    };
    auto pit = kTable.find(preset.empty() ? "default" : preset);
    const auto& row = (pit != kTable.end()) ? pit->second : kTable.at("default");
    auto bit = row.find(b_type);
    return (bit != row.end()) ? bit->second : 0.62;
}

double round3(double v) {
    return std::round(v * 1000.0) / 1000.0;
}

double round4(double v) {
    return std::round(v * 10000.0) / 10000.0;
}

}  // namespace

nlohmann::json DetectedBox::to_json() const {
    nlohmann::json j = {
        {"id", id},
        {"x", x},
        {"y", y},
        {"w", w},
        {"h", h},
        {"area", area},
        {"extent", std::round(extent * 100.0) / 100.0},
        {"contrast", std::round(contrast * 10.0) / 10.0},
        {"type", type},
        {"source", source},
        {"confidence", confidence},
        {"score", score},
        {"depth", depth},
        {"rating_source", rating_source},
    };
    if (edge_score) j["edge_score"] = round3(*edge_score);
    if (interior_edge) j["interior_edge"] = round3(*interior_edge);
    if (!label.empty()) j["label"] = label;
    if (!title.empty()) j["title"] = title;
    if (!wm_class.empty()) j["class"] = wm_class;
    if (is_client) {
        j["is_client"] = true;
        j["floating"] = floating;
        j["pinned"] = pinned;
        j["is_layer"] = is_layer;
        j["focusHistoryID"] = focus_history_id;
    }
    return j;
}

fs::path RatingEngine::resolve_profile_path(const nlohmann::json& rating_cfg) {
    if (rating_cfg.is_object()) {
        std::string explicit_p = rating_cfg.value("profilePath", std::string());
        if (!explicit_p.empty()) {
            return fs::path(ConfigManager::expand_home(explicit_p));
        }
    }
    return ConfigManager::resolve_state_dir() / "rating_profile.json";
}

RatingProfile RatingEngine::load_profile(const fs::path& path) {
    RatingProfile p;
    std::error_code ec;
    if (path.empty() || !fs::is_regular_file(path, ec)) return p;
    std::ifstream f(path);
    if (!f) return p;
    try {
        auto j = nlohmann::json::parse(f);
        if (!j.is_object()) return p;
        p.version = j.value("version", 1);
        p.samples = j.value("samples", 0);
        if (j.contains("biases") && j["biases"].is_object()) {
            for (auto it = j["biases"].begin(); it != j["biases"].end(); ++it) {
                if (it.value().is_number()) {
                    p.biases[it.key()] = it.value().get<double>();
                }
            }
        }
    } catch (...) {
    }
    return p;
}

bool RatingEngine::save_profile(const RatingProfile& profile, const fs::path& path) {
    if (path.empty()) return false;
    std::error_code ec;
    if (path.has_parent_path()) fs::create_directories(path.parent_path(), ec);
    nlohmann::json j = {
        {"version", profile.version},
        {"samples", profile.samples},
        {"biases", profile.biases},
    };
    fs::path tmp = path;
    tmp += ".tmp." + std::to_string(getpid());
    {
        std::ofstream f(tmp, std::ios::binary | std::ios::trunc);
        if (!f) return false;
        f << j.dump(2) << '\n';
        if (!f) return false;
    }
    fs::rename(tmp, path, ec);
    return !ec;
}

std::string RatingEngine::size_bucket(int w, int h) {
    long long area = std::max(1LL, static_cast<long long>(w) * static_cast<long long>(h));
    if (area < 1200) return "xs";
    if (area < 12000) return "sm";
    if (area < 90000) return "md";
    if (area < 450000) return "lg";
    return "xl";
}

std::string RatingEngine::profile_key(const std::string& box_type, int w, int h, const std::string& preset_key) {
    return (preset_key.empty() ? "default" : preset_key) + ":" +
           (box_type.empty() ? "detected" : box_type) + ":" +
           size_bucket(w, h);
}

RatingProfile RatingEngine::record_feedback(const std::string& box_type,
                                            int w, int h,
                                            bool liked,
                                            const std::string& preset_key,
                                            const nlohmann::json& cfg,
                                            const fs::path& explicit_profile) {
    const auto rating_cfg = (cfg.contains("rating") && cfg["rating"].is_object())
                                ? cfg["rating"]
                                : nlohmann::json::object();
    fs::path path = explicit_profile.empty() ? resolve_profile_path(rating_cfg) : explicit_profile;
    RatingProfile prof = load_profile(path);
    if (!rating_cfg.value("adaptiveLearning", true)) return prof;

    double lr = rating_cfg.value("learningRate", 0.08);
    if (lr <= 0.0) lr = 0.08;
    double target = liked ? 0.25 : -0.25;
    std::string key = profile_key(box_type, w, h, preset_key);
    double cur = prof.biases.contains(key) ? prof.biases[key] : 0.0;
    double updated = std::clamp(cur + lr * (target - cur), -0.25, 0.25);
    prof.biases[key] = round4(updated);
    prof.samples += 1;
    save_profile(prof, path);
    return prof;
}

std::pair<double, int> RatingEngine::score_box(const DetectedBox& box,
                                               const std::string& active_preset,
                                               const nlohmann::json& rating_cfg,
                                               const RatingProfile* profile) {
    const nlohmann::json rcfg = rating_cfg.is_object() ? rating_cfg : nlohmann::json::object();
    const nlohmann::json rw = (rcfg.contains("weights") && rcfg["weights"].is_object())
                                  ? rcfg["weights"]
                                  : nlohmann::json::object();

    double w_contrast = std::max(0.0, rw.value("contrast", 0.24));
    double w_geometry = std::max(0.0, rw.value("geometry", 0.18));
    double w_edge = std::max(0.0, rw.value("edge", 0.22));
    double w_interior = std::max(0.0, rw.value("interior", 0.14));
    double w_semantic = std::max(0.0, rw.value("semantic", 0.12));
    double w_preset = std::max(0.0, rw.value("presetFit", 0.10));
    double w_sum = w_contrast + w_geometry + w_edge + w_interior + w_semantic + w_preset;
    if (w_sum <= 0.0) w_sum = 1.0;

    int bw = std::max(1, box.w);
    int bh = std::max(1, box.h);
    bool adaptive = rcfg.value("adaptiveLearning", true);

    if (box.source == "ai" || box.type == "ai") {
        double base = std::clamp(box.ai_confidence > 0.0 ? box.ai_confidence : box.confidence, 0.05, 0.99);
        double bias = 0.0;
        if (profile && adaptive) {
            auto it = profile->biases.find(profile_key(box.type, bw, bh, active_preset));
            if (it != profile->biases.end()) bias = it->second;
        }
        double conf = round3(std::clamp(base + bias, 0.0, 1.0));
        return {conf, static_cast<int>(std::lround(conf * 100.0))};
    }

    if (box.is_client || box.type == "window" || box.type == "floating_window") {
        double conf = (box.type == "floating_window") ? 0.98 : 0.96;
        return {conf, static_cast<int>(std::lround(conf * 100.0))};
    }

    double contrast_s = std::clamp(box.contrast / 32.0, 0.0, 1.0);
    double aspect = static_cast<double>(std::max(bw, bh)) / static_cast<double>(std::min(bw, bh));
    double aspect_penalty = (aspect <= 18.0) ? 0.0 : std::min(0.45, (aspect - 18.0) * 0.02);
    double geometry_s = std::clamp((box.extent * 0.9 + 0.15) - aspect_penalty, 0.0, 1.0);

    double edge_s = 0.84;
    if (box.edge_score) {
        edge_s = std::clamp(*box.edge_score, 0.0, 1.0);
    } else if (box.type == "text" || box.type == "text_block" || box.type == "grid_row" ||
               box.type == "grid_container" || box.type == "content") {
        edge_s = 0.84;
    } else {
        edge_s = std::min(1.0, 0.55 + contrast_s * 0.40);
    }

    double interior_s = 0.82;
    if (box.interior_edge) {
        interior_s = std::clamp(1.0 - std::max(0.0, *box.interior_edge - 0.18) * 1.15, 0.0, 1.0);
    }

    auto sem_it = kBaseTypeScore.find(box.type);
    double semantic_s = (sem_it != kBaseTypeScore.end()) ? sem_it->second : 0.62;
    double preset_s = preset_type_fit(active_preset, box.type);

    double raw_score = (contrast_s * w_contrast + geometry_s * w_geometry + edge_s * w_edge +
                        interior_s * w_interior + semantic_s * w_semantic + preset_s * w_preset) /
                       w_sum;

    double bias = 0.0;
    if (profile && adaptive) {
        auto it = profile->biases.find(profile_key(box.type, bw, bh, active_preset));
        if (it != profile->biases.end()) bias = it->second;
    }

    double conf = round3(std::clamp(raw_score + bias, 0.0, 1.0));
    return {conf, static_cast<int>(std::lround(conf * 100.0))};
}

std::vector<DetectedBox> RatingEngine::rate_and_filter(const std::vector<DetectedBox>& boxes,
                                                      const std::string& active_preset,
                                                      const nlohmann::json& cfg,
                                                      const fs::path& explicit_profile) {
    const auto rating_cfg = (cfg.contains("rating") && cfg["rating"].is_object())
                                ? cfg["rating"]
                                : nlohmann::json::object();
    bool enabled = rating_cfg.value("enabled", true);
    double min_conf = rating_cfg.value("minConfidence", 0.30);

    std::optional<RatingProfile> profile;
    if (enabled) {
        fs::path path = explicit_profile.empty() ? resolve_profile_path(rating_cfg) : explicit_profile;
        profile = load_profile(path);
    }

    std::vector<DetectedBox> out;
    out.reserve(boxes.size());
    for (auto item : boxes) {
        if (!enabled) {
            item.confidence = round3(item.confidence);
            item.score = static_cast<int>(std::lround(item.confidence * 100.0));
            out.push_back(std::move(item));
            continue;
        }

        auto [conf, score_pct] = score_box(item, active_preset, rating_cfg, profile ? &(*profile) : nullptr);
        item.confidence = conf;
        item.score = score_pct;
        if (item.source == "ai") {
            item.rating_source = "ai";
        } else if (profile && profile->samples > 0) {
            item.rating_source = "adaptive";
        } else {
            item.rating_source = "heuristic";
        }

        if (item.is_client || item.type == "window" || item.type == "floating_window" ||
            item.type == "ai" || conf >= min_conf) {
            out.push_back(std::move(item));
        }
    }
    return out;
}

}  // namespace hss
