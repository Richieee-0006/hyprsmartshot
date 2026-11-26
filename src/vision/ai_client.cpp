#include "vision/ai_client.hpp"
#include "core/config.hpp"

#include <algorithm>
#include <cmath>
#include <curl/curl.h>
#include <fstream>
#include <regex>
#include <set>

namespace hss {

namespace {

struct HttpResponse {
    long status = 0;
    std::string body;
    std::string error;
};

size_t curl_write_cb(char* ptr, size_t size, size_t nmemb, void* userdata) {
    auto* out = static_cast<std::string*>(userdata);
    out->append(ptr, size * nmemb);
    return size * nmemb;
}

HttpResponse http_request(const std::string& url,
                          const std::string& method,
                          const std::string& body,
                          const std::vector<std::string>& headers,
                          long timeout_ms) {
    HttpResponse resp;
    CURL* curl = curl_easy_init();
    if (!curl) {
        resp.error = "curl_easy_init failed";
        return resp;
    }

    curl_slist* hdr_list = nullptr;
    for (const auto& h : headers) hdr_list = curl_slist_append(hdr_list, h.c_str());

    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, hdr_list);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, curl_write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &resp.body);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT_MS, std::max(1000L, timeout_ms));
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT_MS, std::min(5000L, std::max(1000L, timeout_ms)));
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);

    if (method == "POST") {
        curl_easy_setopt(curl, CURLOPT_POST, 1L);
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body.c_str());
        curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, static_cast<long>(body.size()));
    }

    CURLcode rc = curl_easy_perform(curl);
    if (rc != CURLE_OK) {
        resp.error = curl_easy_strerror(rc);
    } else {
        curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &resp.status);
    }

    if (hdr_list) curl_slist_free_all(hdr_list);
    curl_easy_cleanup(curl);
    return resp;
}

std::string strip_think_tags(const std::string& text) {
    static const std::regex re(R"(<think>[\s\S]*?</think>)");
    std::string cleaned = std::regex_replace(text, re, "");
    auto not_ws = [](unsigned char c) { return !std::isspace(c); };
    cleaned.erase(cleaned.begin(), std::find_if(cleaned.begin(), cleaned.end(), not_ws));
    cleaned.erase(std::find_if(cleaned.rbegin(), cleaned.rend(), not_ws).base(), cleaned.end());
    return cleaned;
}

std::string rstrip_slash(std::string s) {
    while (!s.empty() && s.back() == '/') s.pop_back();
    return s;
}

std::pair<bool, std::string> dispatch_vlm(const std::string& b64_img,
                                          const std::string& prompt_text,
                                          const nlohmann::json& cfg) {
    auto [provider, prov_cfg] = AiClient::resolve_provider(cfg);
    const auto ai_cfg = (cfg.contains("ai") && cfg["ai"].is_object()) ? cfg["ai"] : nlohmann::json::object();
    long timeout_ms = std::max(2000L, ai_cfg.value("timeoutMs", 35000L));

    std::string api_key = ConfigManager::resolve_api_key(prov_cfg);
    std::string base_url = rstrip_slash(prov_cfg.value("baseUrl", std::string("http://127.0.0.1:8080/v1")));
    std::string model = prov_cfg.value("model", std::string());

    if (provider == "gemini" && !base_url.ends_with("/openai")) {
        if (api_key.empty()) {
            return {false, "Missing Gemini API key (set GEMINI_API_KEY or ai.providers.gemini.apiKey)"};
        }
        if (model.empty()) model = "gemini-3.5-flash-lite";
        std::string url = base_url + "/models/" + model + ":generateContent?key=" + api_key;
        nlohmann::json payload = {
            {"contents", nlohmann::json::array({
                {{"parts", nlohmann::json::array({
                    {{"text", prompt_text}},
                    {{"inline_data", {{"mime_type", "image/jpeg"}, {"data", b64_img}}}},
                })}}
            })},
            {"generationConfig", {{"temperature", 0.1}}},
        };
        auto r = http_request(url, "POST", payload.dump(), {"Content-Type: application/json"}, timeout_ms);
        if (!r.error.empty()) return {false, r.error};
        if (r.status < 200 || r.status >= 300) {
            return {false, "HTTP " + std::to_string(r.status) + ": " + r.body.substr(0, 160)};
        }
        try {
            auto j = nlohmann::json::parse(r.body);
            std::string out;
            if (j.contains("candidates") && j["candidates"].is_array() && !j["candidates"].empty()) {
                const auto& parts = j["candidates"][0]["content"]["parts"];
                if (parts.is_array()) {
                    for (const auto& p : parts) {
                        if (p.is_object() && p.contains("text") && p["text"].is_string()) {
                            if (!out.empty()) out.push_back('\n');
                            out += p["text"].get<std::string>();
                        }
                    }
                }
            }
            return {true, out};
        } catch (const std::exception& e) {
            return {false, std::string("Invalid Gemini JSON: ") + e.what()};
        }
    }

    if (model.empty()) {
        return {false, "No AI model configured for provider '" + provider + "'"};
    }

    std::vector<std::string> headers = {"Content-Type: application/json"};
    if (base_url.find(":4141") != std::string::npos) {
        headers.push_back("Copilot-Vision-Request: true");
    }
    if (!api_key.empty()) {
        headers.push_back("Authorization: Bearer " + api_key);
    } else if (base_url.find("kilo.ai") != std::string::npos) {
        headers.push_back("Authorization: Bearer anonymous");
    }

    nlohmann::json img_obj = {{"url", "data:image/jpeg;base64," + b64_img}};
    if (base_url.find(":4141") != std::string::npos) img_obj["detail"] = "low";

    nlohmann::json payload = {
        {"model", model},
        {"temperature", 0.1},
        {"max_tokens", 900},
        {"messages", nlohmann::json::array({
            {{"role", "user"},
             {"content", nlohmann::json::array({
                 {{"type", "text"}, {"text", prompt_text}},
                 {{"type", "image_url"}, {"image_url", img_obj}},
             })}}
        })},
    };
    if (base_url.find("openrouter.ai") != std::string::npos) {
        payload["reasoning"] = {{"effort", "none"}};
    }

    auto r = http_request(base_url + "/chat/completions", "POST", payload.dump(), headers, timeout_ms);
    if (!r.error.empty()) return {false, r.error};
    if (r.status < 200 || r.status >= 300) {
        return {false, "HTTP " + std::to_string(r.status) + ": " + r.body.substr(0, 160)};
    }

    try {
        auto j = nlohmann::json::parse(r.body);
        if (!j.contains("choices") || !j["choices"].is_array() || j["choices"].empty()) {
            return {true, ""};
        }
        const auto& msg = j["choices"][0]["message"];
        std::string out;
        if (msg.contains("content")) {
            if (msg["content"].is_string()) {
                out = msg["content"].get<std::string>();
            } else if (msg["content"].is_array()) {
                for (const auto& part : msg["content"]) {
                    if (part.is_object() && part.contains("text") && part["text"].is_string()) {
                        if (!out.empty()) out.push_back('\n');
                        out += part["text"].get<std::string>();
                    }
                }
            }
        }
        if (out.empty() && msg.contains("reasoning") && msg["reasoning"].is_string()) {
            out = msg["reasoning"].get<std::string>();
        }
        return {true, out};
    } catch (const std::exception& e) {
        return {false, std::string("Invalid VLM JSON: ") + e.what()};
    }
}

}  // namespace

std::pair<std::string, nlohmann::json> AiClient::resolve_provider(const nlohmann::json& cfg,
                                                                  const std::string& override_provider) {
    const auto ai_cfg = (cfg.contains("ai") && cfg["ai"].is_object()) ? cfg["ai"] : nlohmann::json::object();
    std::string provider = override_provider.empty()
                               ? ai_cfg.value("provider", std::string("openai_compatible"))
                               : override_provider;
    if (provider.empty()) provider = "openai_compatible";
    nlohmann::json prov_cfg = nlohmann::json::object();
    if (ai_cfg.contains("providers") && ai_cfg["providers"].is_object() &&
        ai_cfg["providers"].contains(provider) && ai_cfg["providers"][provider].is_object()) {
        prov_cfg = ai_cfg["providers"][provider];
    }
    return {provider, prov_cfg};
}

std::vector<DetectedBox> AiClient::extract_ai_boxes(const std::string& raw_text,
                                                    int crop_w, int crop_h,
                                                    int offset_x, int offset_y) {
    std::string cleaned = strip_think_tags(raw_text);
    auto lbr = cleaned.find('[');
    auto rbr = cleaned.rfind(']');
    if (lbr == std::string::npos || rbr == std::string::npos || rbr <= lbr) return {};

    std::string slice = cleaned.substr(lbr, rbr - lbr + 1);
    nlohmann::json items = nlohmann::json::array();
    try {
        auto parsed = nlohmann::json::parse(slice);
        if (parsed.is_array()) items = std::move(parsed);
    } catch (...) {
        static const std::regex obj_re(R"(\{[^{}]+\})");
        for (auto it = std::sregex_iterator(slice.begin(), slice.end(), obj_re);
             it != std::sregex_iterator(); ++it) {
            try {
                items.push_back(nlohmann::json::parse(it->str()));
            } catch (...) {
            }
        }
    }

    static const std::set<std::string> kValidTypes = {
        "panel", "button", "input", "slot", "text_block", "text", "detected", "ai"};
    static const std::unordered_map<std::string, std::string> kAliases = {
        {"sidebar", "panel"}, {"dialog", "panel"}, {"toolbar", "panel"}, {"header", "panel"},
        {"dock", "panel"}, {"card", "panel"}, {"window", "panel"}, {"search", "input"},
    };

    std::vector<DetectedBox> boxes;
    for (const auto& item : items) {
        if (!item.is_object()) continue;
        double x1n = 0, y1n = 0, x2n = 0, y2n = 0;
        bool has_coords = false;

        if (item.contains("x1") && item.contains("y1") && item.contains("x2") && item.contains("y2") &&
            item["x1"].is_number() && item["y1"].is_number() && item["x2"].is_number() && item["y2"].is_number()) {
            x1n = item["x1"].get<double>();
            y1n = item["y1"].get<double>();
            x2n = item["x2"].get<double>();
            y2n = item["y2"].get<double>();
            has_coords = true;
        } else if (item.contains("box") && item["box"].is_array() && item["box"].size() == 4) {
            try {
                x1n = item["box"][0].get<double>();
                y1n = item["box"][1].get<double>();
                x2n = item["box"][2].get<double>();
                y2n = item["box"][3].get<double>();
                has_coords = true;
            } catch (...) {}
        } else {
            for (const char* k : {"bbox_2d", "box_2d", "bbox"}) {
                if (item.contains(k) && item[k].is_array() && item[k].size() == 4) {
                    try {
                        y1n = item[k][0].get<double>();
                        x1n = item[k][1].get<double>();
                        y2n = item[k][2].get<double>();
                        x2n = item[k][3].get<double>();
                        has_coords = true;
                    } catch (...) {}
                    break;
                }
            }
        }
        if (!has_coords) continue;

        double scale_x = (std::max(std::abs(x1n), std::abs(x2n)) <= 1.0) ? static_cast<double>(crop_w)
                                                                          : (crop_w / 1000.0);
        double scale_y = (std::max(std::abs(y1n), std::abs(y2n)) <= 1.0) ? static_cast<double>(crop_h)
                                                                          : (crop_h / 1000.0);

        int px1 = std::clamp(static_cast<int>(std::lround(std::min(x1n, x2n) * scale_x)), 0, crop_w) + offset_x;
        int py1 = std::clamp(static_cast<int>(std::lround(std::min(y1n, y2n) * scale_y)), 0, crop_h) + offset_y;
        int px2 = std::clamp(static_cast<int>(std::lround(std::max(x1n, x2n) * scale_x)), 0, crop_w) + offset_x;
        int py2 = std::clamp(static_cast<int>(std::lround(std::max(y1n, y2n) * scale_y)), 0, crop_h) + offset_y;
        int bw = std::max(0, px2 - px1);
        int bh = std::max(0, py2 - py1);
        if (bw < 8 || bh < 8) continue;

        std::string raw_type = item.value("type", std::string("ai"));
        std::transform(raw_type.begin(), raw_type.end(), raw_type.begin(), [](unsigned char c) {
            return static_cast<char>(std::tolower(c));
        });
        if (auto it = kAliases.find(raw_type); it != kAliases.end()) raw_type = it->second;
        std::string b_type = kValidTypes.contains(raw_type) ? raw_type : "ai";

        double conf = 0.88;
        if (item.contains("confidence") && item["confidence"].is_number()) {
            conf = item["confidence"].get<double>();
        }
        conf = std::round(std::clamp(conf, 0.05, 0.99) * 1000.0) / 1000.0;

        DetectedBox b;
        b.x = px1; b.y = py1; b.w = bw; b.h = bh; b.area = bw * bh;
        b.extent = 1.0; b.contrast = 50.0;
        b.type = b_type;
        b.source = "ai";
        b.rating_source = "ai";
        b.ai_confidence = conf;
        b.confidence = conf;
        b.score = static_cast<int>(std::lround(conf * 100.0));
        if (item.contains("label") && item["label"].is_string()) {
            b.label = item["label"].get<std::string>().substr(0, 48);
        }
        boxes.push_back(std::move(b));
    }
    return boxes;
}

void AiClient::snap_to_cv(std::vector<DetectedBox>& ai_boxes,
                          const std::vector<DetectedBox>& cv_boxes,
                          int tol) {
    if (ai_boxes.empty() || cv_boxes.empty()) return;
    for (auto& ab : ai_boxes) {
        int ax1 = ab.x, ay1 = ab.y, ax2 = ab.x + ab.w, ay2 = ab.y + ab.h;
        const DetectedBox* best = nullptr;
        int best_dist = tol * 4 + 1;
        for (const auto& cb : cv_boxes) {
            int dx1 = std::abs(ax1 - cb.x);
            int dy1 = std::abs(ay1 - cb.y);
            int dx2 = std::abs(ax2 - (cb.x + cb.w));
            int dy2 = std::abs(ay2 - (cb.y + cb.h));
            if (dx1 <= tol && dy1 <= tol && dx2 <= tol && dy2 <= tol) {
                int dist = dx1 + dy1 + dx2 + dy2;
                if (dist < best_dist) {
                    best_dist = dist;
                    best = &cb;
                }
            }
        }
        if (best) {
            ab.x = best->x;
            ab.y = best->y;
            ab.w = best->w;
            ab.h = best->h;
            ab.area = best->w * best->h;
        }
    }
}

AiBoxesResult AiClient::detect_boxes(const PixelBuffer& img,
                                     const nlohmann::json& cfg,
                                     const std::vector<DetectedBox>& cv_boxes,
                                     const std::string& custom_prompt) {
    AiBoxesResult res;
    if (img.empty()) {
        res.error = "Empty image";
        return res;
    }

    const auto ai_cfg = (cfg.contains("ai") && cfg["ai"].is_object()) ? cfg["ai"] : nlohmann::json::object();
    int max_dim = ai_cfg.value("maxImageDim", 960);
    auto jpeg = ImageOps::encode_jpeg_resized(img, max_dim, 85);
    std::string b64 = ImageOps::base64_encode(jpeg);

    std::string prompt = custom_prompt.empty() ? ai_cfg.value("prompt", std::string()) : custom_prompt;
    if (prompt.empty()) {
        prompt = ConfigManager::default_config()["ai"]["prompt"].get<std::string>();
    }

    auto [ok, raw] = dispatch_vlm(b64, prompt, cfg);
    if (!ok) {
        res.error = raw;
        return res;
    }

    res.boxes = extract_ai_boxes(raw, img.width, img.height, 0, 0);
    snap_to_cv(res.boxes, cv_boxes, 24);
    res.ok = true;
    return res;
}

AiActionResult AiClient::run_vision_action(const PixelBuffer& cropped,
                                           const std::string& action_mode,
                                           const nlohmann::json& cfg) {
    AiActionResult res;
    if (cropped.empty()) {
        res.error = "Empty crop";
        return res;
    }
    const auto ai_cfg = (cfg.contains("ai") && cfg["ai"].is_object()) ? cfg["ai"] : nlohmann::json::object();
    int max_dim = ai_cfg.value("maxImageDim", 960);
    auto jpeg = ImageOps::encode_jpeg_resized(cropped, max_dim, 88);
    std::string b64 = ImageOps::base64_encode(jpeg);

    std::string prompt = (action_mode == "describe")
                             ? "Concisely describe what is shown in this UI screenshot in 1-3 clear sentences."
                             : "Extract all readable text verbatim, preserving line breaks and table layout. Output text only.";

    auto [ok, raw] = dispatch_vlm(b64, prompt, cfg);
    if (!ok) {
        res.error = raw;
        return res;
    }
    res.ok = true;
    res.text = strip_think_tags(raw);
    return res;
}

AiStatus AiClient::check_status(const nlohmann::json& cfg) {
    AiStatus st;
    const auto ai_cfg = (cfg.contains("ai") && cfg["ai"].is_object()) ? cfg["ai"] : nlohmann::json::object();
    st.enabled = ai_cfg.value("enabled", false);
    st.trigger = ai_cfg.value("trigger", std::string("manual"));
    auto [prov, pcfg] = resolve_provider(cfg);
    st.provider = prov;
    st.model = pcfg.value("model", std::string());

    if (!st.enabled) {
        st.detail = "disabled";
        return st;
    }

    std::string base_url = rstrip_slash(pcfg.value("baseUrl", std::string()));
    std::string api_key = ConfigManager::resolve_api_key(pcfg);
    bool is_local = (base_url.find("127.0.0.1") != std::string::npos ||
                     base_url.find("localhost") != std::string::npos);

    if (!is_local && api_key.empty() && prov != "kilo") {
        st.reachable = false;
        st.detail = "missing API key (" + pcfg.value("apiKeyEnv", std::string()) + ")";
        return st;
    }

    if (is_local) {
        auto r = http_request(base_url + "/models", "GET", "", {}, 2000);
        st.reachable = r.error.empty() && r.status >= 200 && r.status < 500;
        st.detail = st.reachable ? ("ok (" + st.model + ")") : r.error;
    } else {
        st.reachable = true;
        st.detail = "configured (" + st.model + ")";
    }
    return st;
}

std::vector<std::string> AiClient::list_provider_models(const nlohmann::json& cfg,
                                                        const std::string& provider_override,
                                                        bool force_refresh) {
    auto [prov, pcfg] = resolve_provider(cfg, provider_override);
    auto cache_path = ConfigManager::resolve_cache_dir() / "models_cache.json";

    nlohmann::json cache = nlohmann::json::object();
    if (std::ifstream f(cache_path); f) {
        try { cache = nlohmann::json::parse(f); } catch (...) {}
    }
    if (!force_refresh && cache.is_object() && cache.contains(prov) && cache[prov].is_array()) {
        std::vector<std::string> cached;
        for (const auto& m : cache[prov]) {
            if (m.is_string()) cached.push_back(m.get<std::string>());
        }
        if (!cached.empty()) return cached;
    }

    std::string base_url = rstrip_slash(pcfg.value("baseUrl", std::string()));
    std::string api_key = ConfigManager::resolve_api_key(pcfg);
    std::vector<std::string> headers;
    if (!api_key.empty() && prov != "gemini") headers.push_back("Authorization: Bearer " + api_key);

    std::string url = (prov == "gemini" && !base_url.ends_with("/openai"))
                          ? (base_url + "/models?key=" + api_key)
                          : (base_url + "/models");

    auto r = http_request(url, "GET", "", headers, 8000);
    std::vector<std::string> models;
    if (r.error.empty() && r.status >= 200 && r.status < 300) {
        try {
            auto j = nlohmann::json::parse(r.body);
            if (j.contains("data") && j["data"].is_array()) {
                for (const auto& item : j["data"]) {
                    if (item.is_object() && item.contains("id") && item["id"].is_string()) {
                        models.push_back(item["id"].get<std::string>());
                    }
                }
            } else if (j.contains("models") && j["models"].is_array()) {
                for (const auto& item : j["models"]) {
                    if (item.is_object() && item.contains("name") && item["name"].is_string()) {
                        std::string n = item["name"].get<std::string>();
                        if (n.rfind("models/", 0) == 0) n = n.substr(7);
                        models.push_back(std::move(n));
                    }
                }
            }
        } catch (...) {}
    }

    if (!models.empty()) {
        std::sort(models.begin(), models.end());
        models.erase(std::unique(models.begin(), models.end()), models.end());
        std::error_code ec;
        std::filesystem::create_directories(cache_path.parent_path(), ec);
        cache[prov] = models;
        if (std::ofstream out(cache_path, std::ios::trunc); out) {
            out << cache.dump(2) << '\n';
        }
    } else if (pcfg.contains("model") && pcfg["model"].is_string() && !pcfg["model"].get<std::string>().empty()) {
        models.push_back(pcfg["model"].get<std::string>());
    }
    return models;
}

}  // namespace hss
