#include "core/hyprland_ipc.hpp"
#include "core/image_ops.hpp"
#include "vision/ai_client.hpp"
#include "vision/detect_ui.hpp"

#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace {

char* dup_string(const std::string& s) {
    char* out = static_cast<char*>(std::malloc(s.size() + 1));
    if (out) std::memcpy(out, s.c_str(), s.size() + 1);
    return out;
}

}  // namespace

extern "C" {

void hss_vision_free_str(char* ptr) {
    std::free(ptr);
}

char* hss_vision_detect_cv(const uint8_t* bgra, int width, int height, int stride,
                           const char* cfg_json_str,
                           int monitor_x, int monitor_y, double monitor_scale,
                           int active_workspace_id, const char* monitor_name,
                           int logical_w, int logical_h, const char* preset_key) {
    try {
        hss::PixelBuffer img;
        img.width = width;
        img.height = height;
        img.stride = stride;
        img.data.assign(bgra, bgra + static_cast<size_t>(stride) * height);

        nlohmann::json cfg = cfg_json_str ? nlohmann::json::parse(cfg_json_str) : nlohmann::json::object();

        hss::MonitorInfo mon;
        mon.name = monitor_name ? monitor_name : "";
        mon.x = monitor_x;
        mon.y = monitor_y;
        mon.scale = monitor_scale > 0.0 ? monitor_scale : 1.0;
        mon.width = static_cast<int>(logical_w * mon.scale);
        mon.height = static_cast<int>(logical_h * mon.scale);
        mon.active_workspace_id = active_workspace_id;

        auto clients = hss::HyprlandIpc::get_clients_and_layers(mon);

        hss::CvDetectionOptions opts;
        opts.monitor_x = monitor_x;
        opts.monitor_y = monitor_y;
        opts.monitor_scale = mon.scale;
        opts.active_workspace_id = active_workspace_id;
        opts.preset_key = preset_key ? preset_key : "default";

        auto res = hss::CvDetector::detect(img, clients, cfg, opts);
        nlohmann::json out = {
            {"ok", true},
            {"elapsed_ms", res.elapsed_ms},
            {"boxes", nlohmann::json::array()},
        };
        for (const auto& b : res.boxes) out["boxes"].push_back(b.to_json());
        return dup_string(out.dump());
    } catch (const std::exception& e) {
        return dup_string(nlohmann::json({{"ok", false}, {"error", e.what()}, {"boxes", nlohmann::json::array()}}).dump());
    }
}

char* hss_vision_detect_ai(const uint8_t* bgra, int width, int height, int stride,
                           const char* cfg_json_str, const char* cv_boxes_json_str,
                           const char* custom_prompt) {
    try {
        hss::PixelBuffer img;
        img.width = width;
        img.height = height;
        img.stride = stride;
        img.data.assign(bgra, bgra + static_cast<size_t>(stride) * height);

        nlohmann::json cfg = cfg_json_str ? nlohmann::json::parse(cfg_json_str) : nlohmann::json::object();
        std::vector<hss::DetectedBox> cv_boxes;
        if (cv_boxes_json_str && *cv_boxes_json_str) {
            auto arr = nlohmann::json::parse(cv_boxes_json_str);
            if (arr.is_array()) {
                for (const auto& j : arr) {
                    hss::DetectedBox b;
                    b.x = j.value("x", 0); b.y = j.value("y", 0);
                    b.w = j.value("w", 0); b.h = j.value("h", 0);
                    b.area = b.w * b.h;
                    cv_boxes.push_back(b);
                }
            }
        }

        auto res = hss::AiClient::detect_boxes(img, cfg, cv_boxes, custom_prompt ? custom_prompt : "");
        nlohmann::json out = {
            {"ok", res.ok},
            {"error", res.error},
            {"boxes", nlohmann::json::array()},
        };
        for (const auto& b : res.boxes) out["boxes"].push_back(b.to_json());
        return dup_string(out.dump());
    } catch (const std::exception& e) {
        return dup_string(nlohmann::json({{"ok", false}, {"error", e.what()}, {"boxes", nlohmann::json::array()}}).dump());
    }
}

char* hss_vision_run_ai_action(const uint8_t* bgra, int width, int height, int stride,
                               const char* action_mode, const char* cfg_json_str) {
    try {
        hss::PixelBuffer img;
        img.width = width;
        img.height = height;
        img.stride = stride;
        img.data.assign(bgra, bgra + static_cast<size_t>(stride) * height);
        nlohmann::json cfg = cfg_json_str ? nlohmann::json::parse(cfg_json_str) : nlohmann::json::object();
        auto res = hss::AiClient::run_vision_action(img, action_mode ? action_mode : "ocr", cfg);
        return dup_string(nlohmann::json({{"ok", res.ok}, {"text", res.text}, {"error", res.error}}).dump());
    } catch (const std::exception& e) {
        return dup_string(nlohmann::json({{"ok", false}, {"text", ""}, {"error", e.what()}}).dump());
    }
}

char* hss_vision_check_ai_status(const char* cfg_json_str) {
    try {
        nlohmann::json cfg = cfg_json_str ? nlohmann::json::parse(cfg_json_str) : nlohmann::json::object();
        auto st = hss::AiClient::check_status(cfg);
        return dup_string(nlohmann::json({
            {"enabled", st.enabled},
            {"reachable", st.reachable},
            {"provider", st.provider},
            {"model", st.model},
            {"trigger", st.trigger},
            {"detail", st.detail},
        }).dump());
    } catch (const std::exception& e) {
        return dup_string(nlohmann::json({{"enabled", false}, {"reachable", false}, {"detail", e.what()}}).dump());
    }
}

}  // extern "C"
