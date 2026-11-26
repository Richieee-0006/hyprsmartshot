#pragma once

#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>
#include <vector>

namespace hss {

struct RectI {
    int x = 0;
    int y = 0;
    int w = 0;
    int h = 0;
};

// In-memory 32-bit BGRA (little-endian Cairo ARGB32) image buffer
struct PixelBuffer {
    int width = 0;
    int height = 0;
    int stride = 0;  // bytes per row
    std::vector<uint8_t> data;

    bool empty() const { return width <= 0 || height <= 0 || data.empty(); }
};

class ImageOps {
public:
    // Subpixel endpoint-difference transform (eliminates 1px HiDPI rounding drift)
    static RectI compute_physical_crop(double x, double y, double w, double h,
                                       double scale, int phys_w, int phys_h);

    static PixelBuffer crop(const PixelBuffer& src, const RectI& rect);
    static PixelBuffer make_dimmed_copy(const PixelBuffer& src, double dim_opacity);

    static std::vector<uint8_t> encode_png(const PixelBuffer& img, int compression_level = 4);
    static bool save_png(const PixelBuffer& img, const std::filesystem::path& path, int compression_level = 4);
    static std::optional<PixelBuffer> load_image(const std::filesystem::path& path);

    // Resize preserving aspect ratio (if max_dim > 0) and JPEG encode for AI Vision
    static std::vector<uint8_t> encode_jpeg_resized(const PixelBuffer& img, int max_dim = 960, int quality = 85);
    static std::string base64_encode(const std::vector<uint8_t>& bytes);
};

}  // namespace hss
