#pragma once

#include "core/config.hpp"

#include <optional>
#include <string>

namespace hss {

struct PinOptions {
    std::string image_path;
    std::optional<int> x;
    std::optional<int> y;
    std::optional<int> width;
    std::optional<int> height;
    std::string border_color;
    std::string bg_color;
    int border_width = -1;
    std::optional<bool> delete_source;  // --delete (true) / --keep (false) / auto (nullopt)
};

class PinWindow {
public:
    static bool is_temporary_path(const std::string& path);
    static int run(const PinOptions& opts, const nlohmann::json& cfg);
};

}  // namespace hss
