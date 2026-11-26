#include "core/i18n.hpp"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <vector>

#include <nlohmann/json.hpp>

namespace hss {

namespace fs = std::filesystem;

std::string I18n::sanitize_lang(const std::string& raw) {
    std::string s = raw;
    if (auto dot = s.find('.'); dot != std::string::npos) s.resize(dot);
    s.erase(std::remove_if(s.begin(), s.end(), [](unsigned char c) { return std::isspace(c); }), s.end());
    if (s.empty()) return "en";
    for (unsigned char c : s) {
        if (!(std::isalnum(c) || c == '_' || c == '-')) return "en";
    }
    return s;
}

void I18n::merge_json_file(const fs::path& path) {
    std::error_code ec;
    if (!fs::is_regular_file(path, ec)) return;
    std::ifstream f(path);
    if (!f) return;
    try {
        auto j = nlohmann::json::parse(f);
        if (!j.is_object()) return;
        for (auto it = j.begin(); it != j.end(); ++it) {
            if (it.value().is_string()) {
                strings_[it.key()] = it.value().get<std::string>();
            }
        }
    } catch (...) {
    }
}

void I18n::load(const std::string& lang_code,
                const fs::path& config_dir,
                const fs::path& data_dir) {
    strings_.clear();
    lang_ = sanitize_lang(lang_code);

    std::string base_lang = lang_;
    if (auto sep = base_lang.find_first_of("_-"); sep != std::string::npos) {
        base_lang.resize(sep);
    }

    // Load lowest priority first so user overrides win
    std::vector<fs::path> order = {
        data_dir / "localization" / "en.json",
        config_dir / "localization" / "en.json",
    };
    if (!base_lang.empty() && base_lang != "en" && base_lang != lang_) {
        order.push_back(data_dir / "localization" / (base_lang + ".json"));
        order.push_back(config_dir / "localization" / (base_lang + ".json"));
    }
    if (lang_ != "en") {
        order.push_back(data_dir / "localization" / (lang_ + ".json"));
        order.push_back(config_dir / "localization" / (lang_ + ".json"));
    }

    for (const auto& p : order) {
        merge_json_file(p);
    }
}

std::string I18n::t(const std::string& key, const std::string& fallback) const {
    if (auto it = strings_.find(key); it != strings_.end() && !it->second.empty()) {
        return it->second;
    }
    return fallback.empty() ? key : fallback;
}

std::string I18n::format_path(const std::string& key,
                              const std::string& path_value,
                              const std::string& fallback) const {
    std::string out = t(key, fallback);
    const std::string needle = "{path}";
    size_t pos = 0;
    while ((pos = out.find(needle, pos)) != std::string::npos) {
        out.replace(pos, needle.size(), path_value);
        pos += path_value.size();
    }
    return out;
}

}  // namespace hss
