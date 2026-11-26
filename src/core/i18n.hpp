#pragma once

#include <filesystem>
#include <string>
#include <unordered_map>

namespace hss {

class I18n {
public:
    static std::string sanitize_lang(const std::string& raw);

    void load(const std::string& lang_code,
              const std::filesystem::path& config_dir,
              const std::filesystem::path& data_dir);

    std::string t(const std::string& key, const std::string& fallback = "") const;
    std::string format_path(const std::string& key,
                            const std::string& path_value,
                            const std::string& fallback = "") const;
    const std::string& lang() const { return lang_; }

private:
    void merge_json_file(const std::filesystem::path& path);

    std::string lang_ = "en";
    std::unordered_map<std::string, std::string> strings_;
};

}  // namespace hss
