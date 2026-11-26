#include "core/image_ops.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>

#include <jpeglib.h>
#include <png.h>

namespace hss {

RectI ImageOps::compute_physical_crop(double x, double y, double w, double h,
                                      double scale, int phys_w, int phys_h) {
    double s = (scale > 0.0) ? scale : 1.0;
    int cx1 = std::clamp(static_cast<int>(std::lround(x * s)), 0, std::max(0, phys_w));
    int cy1 = std::clamp(static_cast<int>(std::lround(y * s)), 0, std::max(0, phys_h));
    int cx2 = std::clamp(static_cast<int>(std::lround((x + w) * s)), 0, std::max(0, phys_w));
    int cy2 = std::clamp(static_cast<int>(std::lround((y + h) * s)), 0, std::max(0, phys_h));
    int cw = std::max(1, cx2 - cx1);
    int ch = std::max(1, cy2 - cy1);
    if (cx1 + cw > phys_w) cx1 = std::max(0, phys_w - cw);
    if (cy1 + ch > phys_h) cy1 = std::max(0, phys_h - ch);
    return {cx1, cy1, std::min(cw, phys_w), std::min(ch, phys_h)};
}

PixelBuffer ImageOps::crop(const PixelBuffer& src, const RectI& rect) {
    PixelBuffer out;
    if (src.empty()) return out;
    int x = std::clamp(rect.x, 0, src.width - 1);
    int y = std::clamp(rect.y, 0, src.height - 1);
    int w = std::clamp(rect.w, 1, src.width - x);
    int h = std::clamp(rect.h, 1, src.height - y);

    out.width = w;
    out.height = h;
    out.stride = w * 4;
    out.data.resize(static_cast<size_t>(out.stride) * static_cast<size_t>(h));

    for (int row = 0; row < h; ++row) {
        const uint8_t* src_row = src.data.data() + static_cast<size_t>(y + row) * src.stride + static_cast<size_t>(x) * 4;
        uint8_t* dst_row = out.data.data() + static_cast<size_t>(row) * out.stride;
        std::memcpy(dst_row, src_row, static_cast<size_t>(w) * 4);
    }
    return out;
}

PixelBuffer ImageOps::make_dimmed_copy(const PixelBuffer& src, double dim_opacity) {
    PixelBuffer out;
    if (src.empty()) return out;
    out.width = src.width;
    out.height = src.height;
    out.stride = src.stride;
    out.data.resize(src.data.size());

    double keep = std::clamp(1.0 - dim_opacity, 0.05, 1.0);
    uint8_t lut[256];
    for (int i = 0; i < 256; ++i) {
        lut[i] = static_cast<uint8_t>(std::lround(i * keep));
    }

    const size_t n_pixels = static_cast<size_t>(src.height) * static_cast<size_t>(src.width);
    const uint8_t* sp = src.data.data();
    uint8_t* dp = out.data.data();
    if (src.stride == src.width * 4) {
        for (size_t i = 0; i < n_pixels; ++i) {
            dp[0] = lut[sp[0]];
            dp[1] = lut[sp[1]];
            dp[2] = lut[sp[2]];
            dp[3] = 255;
            sp += 4;
            dp += 4;
        }
    } else {
        for (int y = 0; y < src.height; ++y) {
            const uint8_t* sr = src.data.data() + static_cast<size_t>(y) * src.stride;
            uint8_t* dr = out.data.data() + static_cast<size_t>(y) * out.stride;
            for (int x = 0; x < src.width; ++x) {
                dr[x * 4 + 0] = lut[sr[x * 4 + 0]];
                dr[x * 4 + 1] = lut[sr[x * 4 + 1]];
                dr[x * 4 + 2] = lut[sr[x * 4 + 2]];
                dr[x * 4 + 3] = 255;
            }
        }
    }
    return out;
}

std::vector<uint8_t> ImageOps::encode_png(const PixelBuffer& img, int compression_level) {
    std::vector<uint8_t> out;
    if (img.empty()) return out;

    png_structp png = png_create_write_struct(PNG_LIBPNG_VER_STRING, nullptr, nullptr, nullptr);
    if (!png) return out;
    png_infop info = png_create_info_struct(png);
    if (!info) {
        png_destroy_write_struct(&png, nullptr);
        return out;
    }

    if (setjmp(png_jmpbuf(png))) {
        png_destroy_write_struct(&png, &info);
        out.clear();
        return out;
    }

    out.reserve(static_cast<size_t>(img.width) * static_cast<size_t>(img.height) / 2 + 4096);
    png_set_write_fn(
        png, &out,
        [](png_structp p, png_bytep data, png_size_t len) {
            auto* vec = static_cast<std::vector<uint8_t>*>(png_get_io_ptr(p));
            vec->insert(vec->end(), data, data + len);
        },
        nullptr);

    int comp = std::clamp(compression_level, 0, 9);
    png_set_compression_level(png, comp);
    if (comp == 0) {
        png_set_filter(png, 0, PNG_FILTER_NONE);
    }

    png_set_IHDR(png, info, static_cast<png_uint_32>(img.width), static_cast<png_uint_32>(img.height),
                 8, PNG_COLOR_TYPE_RGB, PNG_INTERLACE_NONE,
                 PNG_COMPRESSION_TYPE_DEFAULT, PNG_FILTER_TYPE_DEFAULT);
    png_write_info(png, info);

    std::vector<uint8_t> row_rgb(static_cast<size_t>(img.width) * 3);
    for (int y = 0; y < img.height; ++y) {
        const uint8_t* src = img.data.data() + static_cast<size_t>(y) * img.stride;
        for (int x = 0; x < img.width; ++x) {
            row_rgb[x * 3 + 0] = src[x * 4 + 2];  // R
            row_rgb[x * 3 + 1] = src[x * 4 + 1];  // G
            row_rgb[x * 3 + 2] = src[x * 4 + 0];  // B
        }
        png_write_row(png, row_rgb.data());
    }

    png_write_end(png, nullptr);
    png_destroy_write_struct(&png, &info);
    return out;
}

bool ImageOps::save_png(const PixelBuffer& img, const std::filesystem::path& path, int compression_level) {
    auto bytes = encode_png(img, compression_level);
    if (bytes.empty()) return false;
    std::error_code ec;
    if (path.has_parent_path()) {
        std::filesystem::create_directories(path.parent_path(), ec);
    }
    std::ofstream f(path, std::ios::binary | std::ios::trunc);
    if (!f) return false;
    f.write(reinterpret_cast<const char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
    return f.good();
}

namespace {

std::optional<PixelBuffer> load_png_file(const std::filesystem::path& path) {
    FILE* fp = std::fopen(path.c_str(), "rb");
    if (!fp) return std::nullopt;

    png_byte sig[8];
    if (std::fread(sig, 1, 8, fp) != 8 || png_sig_cmp(sig, 0, 8) != 0) {
        std::fclose(fp);
        return std::nullopt;
    }

    png_structp png = png_create_read_struct(PNG_LIBPNG_VER_STRING, nullptr, nullptr, nullptr);
    if (!png) { std::fclose(fp); return std::nullopt; }
    png_infop info = png_create_info_struct(png);
    if (!info) {
        png_destroy_read_struct(&png, nullptr, nullptr);
        std::fclose(fp);
        return std::nullopt;
    }

    if (setjmp(png_jmpbuf(png))) {
        png_destroy_read_struct(&png, &info, nullptr);
        std::fclose(fp);
        return std::nullopt;
    }

    png_init_io(png, fp);
    png_set_sig_bytes(png, 8);
    png_read_info(png, info);

    int w = static_cast<int>(png_get_image_width(png, info));
    int h = static_cast<int>(png_get_image_height(png, info));
    png_byte color_type = png_get_color_type(png, info);
    png_byte bit_depth = png_get_bit_depth(png, info);

    if (bit_depth == 16) png_set_strip_16(png);
    if (color_type == PNG_COLOR_TYPE_PALETTE) png_set_palette_to_rgb(png);
    if (color_type == PNG_COLOR_TYPE_GRAY && bit_depth < 8) png_set_expand_gray_1_2_4_to_8(png);
    if (png_get_valid(png, info, PNG_INFO_tRNS)) png_set_tRNS_to_alpha(png);
    if (color_type == PNG_COLOR_TYPE_GRAY || color_type == PNG_COLOR_TYPE_GRAY_ALPHA) png_set_gray_to_rgb(png);
    if (!(color_type & PNG_COLOR_MASK_ALPHA)) png_set_filler(png, 0xFF, PNG_FILLER_AFTER);
    png_set_bgr(png);
    png_read_update_info(png, info);

    PixelBuffer out;
    out.width = w;
    out.height = h;
    out.stride = w * 4;
    out.data.resize(static_cast<size_t>(out.stride) * static_cast<size_t>(h));

    std::vector<png_bytep> rows(static_cast<size_t>(h));
    for (int y = 0; y < h; ++y) {
        rows[y] = out.data.data() + static_cast<size_t>(y) * out.stride;
    }
    png_read_image(png, rows.data());
    png_destroy_read_struct(&png, &info, nullptr);
    std::fclose(fp);
    return out;
}

std::optional<PixelBuffer> load_jpeg_file(const std::filesystem::path& path) {
    FILE* fp = std::fopen(path.c_str(), "rb");
    if (!fp) return std::nullopt;

    jpeg_decompress_struct cinfo{};
    jpeg_error_mgr jerr{};
    cinfo.err = jpeg_std_error(&jerr);
    jerr.error_exit = [](j_common_ptr) { throw std::runtime_error("jpeg decode error"); };

    try {
        jpeg_create_decompress(&cinfo);
        jpeg_stdio_src(&cinfo, fp);
        jpeg_read_header(&cinfo, TRUE);
        cinfo.out_color_space = JCS_EXT_BGRA;
        jpeg_start_decompress(&cinfo);

        PixelBuffer out;
        out.width = static_cast<int>(cinfo.output_width);
        out.height = static_cast<int>(cinfo.output_height);
        out.stride = out.width * 4;
        out.data.resize(static_cast<size_t>(out.stride) * static_cast<size_t>(out.height));

        while (cinfo.output_scanline < cinfo.output_height) {
            JSAMPROW row = out.data.data() + static_cast<size_t>(cinfo.output_scanline) * out.stride;
            jpeg_read_scanlines(&cinfo, &row, 1);
        }
        jpeg_finish_decompress(&cinfo);
        jpeg_destroy_decompress(&cinfo);
        std::fclose(fp);
        return out;
    } catch (...) {
        jpeg_destroy_decompress(&cinfo);
        std::fclose(fp);
        return std::nullopt;
    }
}

}  // namespace

std::optional<PixelBuffer> ImageOps::load_image(const std::filesystem::path& path) {
    if (auto png = load_png_file(path)) return png;
    if (auto jpg = load_jpeg_file(path)) return jpg;
    return std::nullopt;
}

std::vector<uint8_t> ImageOps::encode_jpeg_resized(const PixelBuffer& img, int max_dim, int quality) {
    std::vector<uint8_t> out;
    if (img.empty()) return out;

    int dst_w = img.width;
    int dst_h = img.height;
    if (max_dim > 0 && std::max(dst_w, dst_h) > max_dim) {
        double scale = static_cast<double>(max_dim) / static_cast<double>(std::max(dst_w, dst_h));
        dst_w = std::max(1, static_cast<int>(std::lround(dst_w * scale)));
        dst_h = std::max(1, static_cast<int>(std::lround(dst_h * scale)));
    }

    // Fast bilinear resize to RGB
    std::vector<uint8_t> rgb(static_cast<size_t>(dst_w) * static_cast<size_t>(dst_h) * 3);
    for (int y = 0; y < dst_h; ++y) {
        double sy = (dst_h == img.height) ? y : (y + 0.5) * img.height / dst_h - 0.5;
        int y0 = std::clamp(static_cast<int>(std::floor(sy)), 0, img.height - 1);
        int y1 = std::clamp(y0 + 1, 0, img.height - 1);
        double fy = std::clamp(sy - y0, 0.0, 1.0);
        const uint8_t* r0 = img.data.data() + static_cast<size_t>(y0) * img.stride;
        const uint8_t* r1 = img.data.data() + static_cast<size_t>(y1) * img.stride;
        uint8_t* dr = rgb.data() + static_cast<size_t>(y) * dst_w * 3;
        for (int x = 0; x < dst_w; ++x) {
            double sx = (dst_w == img.width) ? x : (x + 0.5) * img.width / dst_w - 0.5;
            int x0 = std::clamp(static_cast<int>(std::floor(sx)), 0, img.width - 1);
            int x1 = std::clamp(x0 + 1, 0, img.width - 1);
            double fx = std::clamp(sx - x0, 0.0, 1.0);
            auto interp = [&](int ch) -> uint8_t {
                double top = r0[x0 * 4 + ch] * (1.0 - fx) + r0[x1 * 4 + ch] * fx;
                double bot = r1[x0 * 4 + ch] * (1.0 - fx) + r1[x1 * 4 + ch] * fx;
                return static_cast<uint8_t>(std::clamp(std::lround(top * (1.0 - fy) + bot * fy), 0L, 255L));
            };
            dr[x * 3 + 0] = interp(2);
            dr[x * 3 + 1] = interp(1);
            dr[x * 3 + 2] = interp(0);
        }
    }

    jpeg_compress_struct cinfo{};
    jpeg_error_mgr jerr{};
    cinfo.err = jpeg_std_error(&jerr);
    jpeg_create_compress(&cinfo);

    unsigned char* mem_buf = nullptr;
    unsigned long mem_size = 0;
    jpeg_mem_dest(&cinfo, &mem_buf, &mem_size);

    cinfo.image_width = static_cast<JDIMENSION>(dst_w);
    cinfo.image_height = static_cast<JDIMENSION>(dst_h);
    cinfo.input_components = 3;
    cinfo.in_color_space = JCS_RGB;
    jpeg_set_defaults(&cinfo);
    jpeg_set_quality(&cinfo, std::clamp(quality, 10, 100), TRUE);
    jpeg_start_compress(&cinfo, TRUE);

    while (cinfo.next_scanline < cinfo.image_height) {
        JSAMPROW row = rgb.data() + static_cast<size_t>(cinfo.next_scanline) * dst_w * 3;
        jpeg_write_scanlines(&cinfo, &row, 1);
    }

    jpeg_finish_compress(&cinfo);
    jpeg_destroy_compress(&cinfo);

    if (mem_buf && mem_size > 0) {
        out.assign(mem_buf, mem_buf + mem_size);
        std::free(mem_buf);
    }
    return out;
}

std::string ImageOps::base64_encode(const std::vector<uint8_t>& bytes) {
    static constexpr char kTable[] =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string out;
    out.reserve(((bytes.size() + 2) / 3) * 4);
    size_t i = 0;
    while (i + 2 < bytes.size()) {
        uint32_t n = (static_cast<uint32_t>(bytes[i]) << 16) |
                     (static_cast<uint32_t>(bytes[i + 1]) << 8) |
                     static_cast<uint32_t>(bytes[i + 2]);
        out.push_back(kTable[(n >> 18) & 63]);
        out.push_back(kTable[(n >> 12) & 63]);
        out.push_back(kTable[(n >> 6) & 63]);
        out.push_back(kTable[n & 63]);
        i += 3;
    }
    if (i < bytes.size()) {
        uint32_t n = static_cast<uint32_t>(bytes[i]) << 16;
        if (i + 1 < bytes.size()) n |= static_cast<uint32_t>(bytes[i + 1]) << 8;
        out.push_back(kTable[(n >> 18) & 63]);
        out.push_back(kTable[(n >> 12) & 63]);
        out.push_back((i + 1 < bytes.size()) ? kTable[(n >> 6) & 63] : '=');
        out.push_back('=');
    }
    return out;
}

}  // namespace hss
