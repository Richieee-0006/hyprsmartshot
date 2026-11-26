#include "vision/detect_ui.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <mutex>
#include <thread>
#include <unordered_map>
#include <unordered_set>

#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#if __has_include(<opencv2/geometry/2d.hpp>)
#include <opencv2/geometry/2d.hpp>
#endif

namespace hss {

namespace {

void configure_opencv_threads_once() {
    static std::once_flag flag;
    std::call_once(flag, [] {
        int hw = static_cast<int>(std::thread::hardware_concurrency());
        cv::setNumThreads(std::clamp(hw > 0 ? hw : 2, 1, 4));
    });
}

inline double sat_mean_i32(const cv::Mat& sat, int x1, int y1, int x2, int y2) {
    if (x2 <= x1 || y2 <= y1) return 0.0;
    double total = static_cast<double>(sat.at<int32_t>(y2, x2)) -
                   static_cast<double>(sat.at<int32_t>(y1, x2)) -
                   static_cast<double>(sat.at<int32_t>(y2, x1)) +
                   static_cast<double>(sat.at<int32_t>(y1, x1));
    return total / static_cast<double>((x2 - x1) * (y2 - y1));
}

inline bool sat_has_std(const cv::Mat& sat, const cv::Mat& sqsat, int x, int y, int w, int h, double min_std) {
    double area = static_cast<double>(w) * static_cast<double>(h);
    if (area <= 0.0) return false;
    double s1 = static_cast<double>(sat.at<int32_t>(y + h, x + w)) -
                static_cast<double>(sat.at<int32_t>(y, x + w)) -
                static_cast<double>(sat.at<int32_t>(y + h, x)) +
                static_cast<double>(sat.at<int32_t>(y, x));
    double s2 = sqsat.at<double>(y + h, x + w) -
                sqsat.at<double>(y, x + w) -
                sqsat.at<double>(y + h, x) +
                sqsat.at<double>(y, x);
    double mean = s1 / area;
    double var = (s2 / area) - (mean * mean);
    return var >= (min_std * min_std);
}

int type_priority(const std::string& t) {
    if (t == "grid_container") return 7;
    if (t == "grid_row") return 6;
    if (t == "slot") return 5;
    if (t == "item" || t == "button" || t == "input") return 4;
    if (t == "text_block" || t == "text") return 3;
    if (t == "panel") return 2;
    return 1;
}

double compute_border_contrast(const cv::Mat& gray, const cv::Mat& sat, int x, int y, int w, int h) {
    int h_img = gray.rows;
    int w_img = gray.cols;
    if (x <= 1 || y <= 1 || x + w >= w_img - 2 || y + h >= h_img - 2) return 30.0;

    int d = (w < 24 || h < 24) ? 1 : ((w < 44 || h < 44) ? 2 : 3);
    int ty_out = std::max(0, y - d);
    int ty_in = std::min(h_img, y + d);
    int by_in = std::max(0, y + h - d);
    int by_out = std::min(h_img, y + h + d);
    int lx_out = std::max(0, x - d);
    int lx_in = std::min(w_img, x + d);
    int rx_in = std::max(0, x + w - d);
    int rx_out = std::min(w_img, x + w + d);

    double diff_t = (y > ty_out && ty_in > y)
                        ? std::abs(sat_mean_i32(sat, x, ty_out, x + w, y) - sat_mean_i32(sat, x, y, x + w, ty_in))
                        : 0.0;
    double diff_b = (y + h > by_in && by_out > y + h)
                        ? std::abs(sat_mean_i32(sat, x, by_in, x + w, y + h) - sat_mean_i32(sat, x, y + h, x + w, by_out))
                        : 0.0;
    double diff_l = (x > lx_out && lx_in > x)
                        ? std::abs(sat_mean_i32(sat, lx_out, y, x, y + h) - sat_mean_i32(sat, x, y, lx_in, y + h))
                        : 0.0;
    double diff_r = (x + w > rx_in && rx_out > x + w)
                        ? std::abs(sat_mean_i32(sat, rx_in, y, x + w, y + h) - sat_mean_i32(sat, x + w, y, rx_out, y + h))
                        : 0.0;

    std::array<double, 4> diffs = {diff_t, diff_b, diff_l, diff_r};
    std::sort(diffs.begin(), diffs.end(), std::greater<double>());
    double best3 = (diffs[0] + diffs[1] + diffs[2]) / 3.0;
    double avg4 = (diffs[0] + diffs[1] + diffs[2] + diffs[3]) / 4.0;
    return std::max(avg4, best3 * 0.92);
}

std::pair<bool, double> is_valid_border(const cv::Mat& gray, const cv::Mat& sat, int x, int y, int w, int h) {
    int h_img = gray.rows;
    int w_img = gray.cols;
    if (x <= 1 || y <= 1 || x + w >= w_img - 2 || y + h >= h_img - 2) return {true, 30.0};

    double local_mean = sat_mean_i32(sat, std::max(0, x), std::max(0, y),
                                     std::min(w_img, x + w), std::min(h_img, y + h));
    double contrast = compute_border_contrast(gray, sat, x, y, w, h);

    double req_contrast = (local_mean < 45.0) ? 1.8 : ((local_mean < 80.0) ? 2.8 : 4.2);
    if (w < 28 || h < 28) req_contrast = std::max(1.8, req_contrast * 0.85);
    return {contrast >= req_contrast, contrast};
}

std::string to_lower_copy(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return s;
}

std::vector<DetectedBox> detect_window_content_areas(const cv::Mat& gray,
                                                     const std::vector<DetectedBox>& client_boxes) {
    std::vector<DetectedBox> out;
    int h_img = gray.rows;
    int w_img = gray.cols;

    for (const auto& win : client_boxes) {
        if (win.is_layer) continue;
        int wx = std::max(0, win.x);
        int wy = std::max(0, win.y);
        int ww = std::min(w_img - wx, win.w);
        int wh = std::min(h_img - wy, win.h);
        if (ww < 180 || wh < 150) continue;

        cv::Mat win_sub = gray(cv::Rect(wx, wy, ww, wh));

        // 1. Browser header / page body viewport
        if (ww >= 300 && wh >= 200) {
            int header_min_y = wy + 40;
            int header_max_y = wy + std::min(160, static_cast<int>(wh * 0.35));
            if (header_max_y > header_min_y && header_max_y < h_img && (header_max_y - header_min_y) >= 5 && ww >= 100) {
                cv::Mat sub_gray = gray(cv::Rect(wx, header_min_y, ww, header_max_y - header_min_y));
                int best_row = -1;
                double max_diff = -1.0;
                for (int r = 0; r < sub_gray.rows - 1; ++r) {
                    const uint8_t* p0 = sub_gray.ptr<uint8_t>(r);
                    const uint8_t* p1 = sub_gray.ptr<uint8_t>(r + 1);
                    long sum = 0;
                    for (int c = 0; c < sub_gray.cols; ++c) {
                        sum += std::abs(static_cast<int>(p1[c]) - static_cast<int>(p0[c]));
                    }
                    double mean_d = static_cast<double>(sum) / sub_gray.cols;
                    if (mean_d > max_diff) {
                        max_diff = mean_d;
                        best_row = r;
                    }
                }
                if (best_row >= 0 && max_diff >= 3.5) {
                    int sep_y = header_min_y + best_row + 1;
                    int body_h = (wy + wh) - sep_y;
                    if (body_h >= 100) {
                        DetectedBox b;
                        b.x = wx;
                        b.y = sep_y;
                        b.w = ww;
                        b.h = body_h;
                        b.area = ww * body_h;
                        b.extent = 1.0;
                        b.contrast = 35.0;
                        b.type = "panel";
                        b.title = win.title;
                        b.wm_class = win.wm_class;
                        out.push_back(std::move(b));
                    }
                }
            }
        }

        // 2. Multi-column and sidebar detection (skip 3D game windows)
        std::string cls_low = to_lower_copy(win.wm_class);
        std::string ttl_low = to_lower_copy(win.title);
        bool is_game = false;
        for (const char* g : {"minecraft", "steam_app", "gamescope", "wine", "lutris", "heroic", "retroarch", "unity", "unreal"}) {
            if (cls_low.find(g) != std::string::npos) { is_game = true; break; }
        }
        if (ttl_low.find("multiplayer") != std::string::npos && ttl_low.find("third-party") != std::string::npos) {
            is_game = true;
        }
        if (is_game) continue;

        std::vector<int> col_counts(static_cast<size_t>(std::max(0, ww - 1)), 0);
        for (int r = 0; r < wh; ++r) {
            const uint8_t* p = win_sub.ptr<uint8_t>(r);
            for (int c = 0; c < ww - 1; ++c) {
                if (std::abs(static_cast<int>(p[c + 1]) - static_cast<int>(p[c])) >= 3) {
                    col_counts[c]++;
                }
            }
        }

        std::vector<int> merged_splits;
        int col_thresh = static_cast<int>(std::ceil(wh * 0.40));
        for (int c = 0; c < ww - 1; ++c) {
            if (col_counts[c] >= col_thresh) {
                int s = c + 1;
                if (merged_splits.empty() || (s - merged_splits.back()) > 8) {
                    merged_splits.push_back(s);
                }
            }
        }

        int left_edge = 0;
        int right_edge = ww;
        std::vector<int> col_bounds;
        std::vector<int> inner_splits;
        for (int s : merged_splits) {
            if (s < 36) left_edge = s;
            else if (s > ww - 36) right_edge = s;
            else inner_splits.push_back(s);
        }
        col_bounds.push_back(left_edge);
        col_bounds.insert(col_bounds.end(), inner_splits.begin(), inner_splits.end());
        col_bounds.push_back(right_edge);

        if (col_bounds.size() > 2) {
            for (size_t k = 0; k + 1 < col_bounds.size(); ++k) {
                int cx1 = col_bounds[k];
                int cx2 = col_bounds[k + 1];
                int cw = cx2 - cx1;
                if (cw < 40) continue;

                std::vector<int> merged_row_splits;
                int row_thresh = static_cast<int>(std::ceil(cw * 0.40));
                for (int r = 0; r < wh - 1; ++r) {
                    const uint8_t* p0 = win_sub.ptr<uint8_t>(r) + cx1;
                    const uint8_t* p1 = win_sub.ptr<uint8_t>(r + 1) + cx1;
                    int cnt = 0;
                    for (int c = 0; c < cw; ++c) {
                        if (std::abs(static_cast<int>(p1[c]) - static_cast<int>(p0[c])) >= 3) cnt++;
                    }
                    if (cnt >= row_thresh) {
                        int rs = r + 1;
                        if (merged_row_splits.empty() || (rs - merged_row_splits.back()) > 8) {
                            merged_row_splits.push_back(rs);
                        }
                    }
                }

                int top_edge = 0;
                int bottom_edge = wh;
                std::vector<int> inner_rows;
                for (int rs : merged_row_splits) {
                    if (rs < 36) top_edge = rs;
                    else if (rs > wh - 36) bottom_edge = rs;
                    else inner_rows.push_back(rs);
                }

                std::vector<int> row_bounds;
                row_bounds.push_back(top_edge);
                row_bounds.insert(row_bounds.end(), inner_rows.begin(), inner_rows.end());
                row_bounds.push_back(bottom_edge);

                DetectedBox col_box;
                col_box.x = wx + cx1;
                col_box.y = wy + top_edge;
                col_box.w = cw;
                col_box.h = bottom_edge - top_edge;
                col_box.area = col_box.w * col_box.h;
                col_box.extent = 1.0;
                col_box.contrast = 28.0;
                col_box.type = "panel";
                col_box.title = win.title;
                col_box.wm_class = win.wm_class;
                out.push_back(col_box);

                if (row_bounds.size() > 2) {
                    for (size_t rk = 0; rk + 1 < row_bounds.size(); ++rk) {
                        int ry1 = row_bounds[rk];
                        int ry2 = row_bounds[rk + 1];
                        int rh = ry2 - ry1;
                        if (rh >= 24 && rh != (bottom_edge - top_edge)) {
                            DetectedBox sub;
                            sub.x = wx + cx1;
                            sub.y = wy + ry1;
                            sub.w = cw;
                            sub.h = rh;
                            sub.area = cw * rh;
                            sub.extent = 1.0;
                            sub.contrast = 30.0;
                            sub.type = (rh >= 24 && rh <= 80 && ry2 >= wh - 100) ? "input" : "panel";
                            sub.title = win.title;
                            sub.wm_class = win.wm_class;
                            out.push_back(std::move(sub));
                        }
                    }
                }
            }
        }
    }
    return out;
}

DetectedBox make_text_block(const std::vector<DetectedBox>& lines) {
    int px = lines.front().x;
    int py = lines.front().y;
    int px2 = px + lines.front().w;
    int py2 = py + lines.front().h;
    for (const auto& l : lines) {
        px = std::min(px, l.x);
        py = std::min(py, l.y);
        px2 = std::max(px2, l.x + l.w);
        py2 = std::max(py2, l.y + l.h);
    }
    DetectedBox b;
    b.x = px;
    b.y = py;
    b.w = px2 - px;
    b.h = py2 - py;
    b.area = b.w * b.h;
    b.extent = 0.96;
    b.contrast = 35.0;
    b.type = "text_block";
    return b;
}

std::vector<DetectedBox> merge_collinear_text_words(std::vector<DetectedBox> lines) {
    if (lines.size() < 2) return lines;
    std::sort(lines.begin(), lines.end(), [](const DetectedBox& a, const DetectedBox& b) {
        return std::tie(a.y, a.x) < std::tie(b.y, b.x);
    });
    std::vector<DetectedBox> merged;
    merged.reserve(lines.size());
    for (const auto& box : lines) {
        bool joined = false;
        if (box.h >= 24) {
            int by1 = box.y, by2 = box.y + box.h;
            size_t start = merged.size() > 6 ? merged.size() - 6 : 0;
            for (size_t i = merged.size(); i-- > start;) {
                auto& prev = merged[i];
                int py1 = prev.y, py2 = prev.y + prev.h;
                int v_overlap = std::min(by2, py2) - std::max(by1, py1);
                int min_h = std::min(box.h, prev.h);
                if (min_h >= 24 && v_overlap >= min_h * 0.55) {
                    int gap = box.x - (prev.x + prev.w);
                    int max_gap = std::max(18, static_cast<int>(min_h * 0.65));
                    if (gap >= -4 && gap <= max_gap) {
                        int nx = std::min(prev.x, box.x);
                        int ny = std::min(prev.y, box.y);
                        int nx2 = std::max(prev.x + prev.w, box.x + box.w);
                        int ny2 = std::max(prev.y + prev.h, box.y + box.h);
                        prev.x = nx;
                        prev.y = ny;
                        prev.w = nx2 - nx;
                        prev.h = ny2 - ny;
                        prev.area = prev.w * prev.h;
                        joined = true;
                        break;
                    }
                }
            }
        }
        if (!joined) merged.push_back(box);
    }
    return merged;
}

std::vector<DetectedBox> detect_text_regions(const cv::Mat& gray, const cv::Mat& sat,
                                             const cv::Mat& sqsat, const cv::Mat& clahe_gray,
                                             int orig_w, int orig_h,
                                             const nlohmann::json& det_cfg) {
    bool adaptive_text = det_cfg.value("adaptiveTextThreshold", true);
    bool filter_icons = det_cfg.value("filterIconsFromText", true);
    bool multi_col = det_cfg.value("multiColumnParagraphs", true);
    int max_header_h = det_cfg.value("maxHeaderHeight", 96);
    if (max_header_h <= 0) max_header_h = 96;

    cv::Mat sobel_f, grad_x, closed_line, thresh_line;
    cv::Sobel(gray, sobel_f, CV_32F, 1, 0, 3);
    cv::convertScaleAbs(sobel_f, grad_x);
    cv::Mat k_line = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(17, 3));
    cv::morphologyEx(grad_x, closed_line, cv::MORPH_CLOSE, k_line);
    cv::threshold(closed_line, thresh_line, 0, 255, cv::THRESH_BINARY | cv::THRESH_OTSU);

    double min_std = 6.0;
    if (adaptive_text) {
        cv::Mat sobel_cl, grad_cl, closed_cl, thresh_cl;
        cv::Sobel(clahe_gray, sobel_cl, CV_32F, 1, 0, 3);
        cv::convertScaleAbs(sobel_cl, grad_cl);
        cv::morphologyEx(grad_cl, closed_cl, cv::MORPH_CLOSE, k_line);
        cv::threshold(closed_cl, thresh_cl, 48, 255, cv::THRESH_BINARY);
        cv::bitwise_or(thresh_line, thresh_cl, thresh_line);
        min_std = 4.5;
    }

    std::vector<std::vector<cv::Point>> contours_line;
    cv::findContours(thresh_line, contours_line, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);

    std::vector<DetectedBox> raw_lines;
    for (const auto& cnt : contours_line) {
        cv::Rect r = cv::boundingRect(cnt);
        if (r.width < 18 || r.height < 8 || r.height > max_header_h) continue;
        if (sat_has_std(sat, sqsat, r.x, r.y, r.width, r.height, min_std)) {
            DetectedBox b;
            b.x = r.x;
            b.y = r.y;
            b.w = r.width;
            b.h = r.height;
            b.area = r.width * r.height;
            b.extent = 0.95;
            b.contrast = 30.0;
            b.type = "text";
            raw_lines.push_back(std::move(b));
        }
    }

    std::vector<DetectedBox> text_boxes = merge_collinear_text_words(std::move(raw_lines));
    if (filter_icons) {
        std::erase_if(text_boxes, [](const DetectedBox& b) {
            return b.w <= 56 && b.h >= 22 && (static_cast<double>(b.w) / b.h) < 1.55;
        });
    }

    auto para_boxes = CvDetector::cluster_text_paragraphs(text_boxes, 2, multi_col);
    for (auto& p : para_boxes) {
        if (p.w >= orig_w * 0.85 && p.h >= orig_h * 0.65) continue;
        if (filter_icons && (p.w < 48 || (static_cast<double>(p.w) / p.h) < 0.80)) continue;
        text_boxes.push_back(std::move(p));
    }

    cv::Mat k_para_h = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(17, 1));
    cv::Mat k_para_v = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(9, 14));
    cv::Mat closed_h, closed_para;
    cv::morphologyEx(thresh_line, closed_h, cv::MORPH_CLOSE, k_para_h);
    cv::morphologyEx(closed_h, closed_para, cv::MORPH_CLOSE, k_para_v);

    std::vector<std::vector<cv::Point>> contours_para;
    cv::findContours(closed_para, contours_para, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);
    for (const auto& cnt : contours_para) {
        cv::Rect r = cv::boundingRect(cnt);
        if (r.width >= orig_w * 0.85 && r.height >= orig_h * 0.65) continue;
        if (filter_icons && (r.width < 48 || (static_cast<double>(r.width) / r.height) < 0.80)) continue;

        bool is_single = false;
        for (const auto& t : text_boxes) {
            if (t.type == "text" &&
                std::abs(t.x - r.x) <= 6 && std::abs(t.y - r.y) <= 6 &&
                std::abs(t.w - r.width) <= 10 && std::abs(t.h - r.height) <= 10) {
                is_single = true;
                break;
            }
        }
        if (is_single) continue;
        if (r.width >= 36 && r.height >= 26 && (r.width * r.height) >= 1000) {
            if (sat_has_std(sat, sqsat, r.x, r.y, r.width, r.height, min_std)) {
                DetectedBox b;
                b.x = r.x;
                b.y = r.y;
                b.w = r.width;
                b.h = r.height;
                b.area = r.width * r.height;
                b.extent = 0.96;
                b.contrast = 35.0;
                b.type = "text_block";
                text_boxes.push_back(std::move(b));
            }
        }
    }

    return text_boxes;
}

}  // namespace

std::vector<DetectedBox> CvDetector::deduplicate_boxes(const std::vector<DetectedBox>& boxes,
                                                       double iou_thresh,
                                                       double contain_thresh) {
    std::vector<DetectedBox> sorted = boxes;
    std::stable_sort(sorted.begin(), sorted.end(), [](const DetectedBox& a, const DetectedBox& b) {
        return a.area > b.area;
    });

    struct Meta {
        int x, y, x2, y2, w, h, area;
        bool is_client;
        int gx, gy;
    };

    constexpr int kCellSize = 32;
    auto cell_key = [](int gx, int gy) -> int64_t {
        return (static_cast<int64_t>(gx) << 32) ^ static_cast<uint32_t>(gy);
    };

    std::vector<DetectedBox> deduped;
    std::vector<Meta> meta;
    std::unordered_map<int64_t, std::vector<size_t>> grid;
    deduped.reserve(sorted.size());
    meta.reserve(sorted.size());

    std::vector<size_t> cand_indices;
    for (const auto& b : sorted) {
        int bx = b.x, by = b.y, bw = b.w, bh = b.h;
        int bx2 = bx + bw, by2 = by + bh;
        int b_area = bw * bh;
        int gx = bx / kCellSize;
        int gy = by / kCellSize;

        cand_indices.clear();
        for (int dx = -1; dx <= 1; ++dx) {
            for (int dy = -1; dy <= 1; ++dy) {
                auto it = grid.find(cell_key(gx + dx, gy + dy));
                if (it != grid.end()) {
                    cand_indices.insert(cand_indices.end(), it->second.begin(), it->second.end());
                }
            }
        }
        if (cand_indices.size() > 1) std::sort(cand_indices.begin(), cand_indices.end());

        bool merged = false;
        for (size_t idx : cand_indices) {
            auto& m = meta[idx];
            if (m.is_client != b.is_client) continue;
            if (std::abs(bx - m.x) > 25 || std::abs(by - m.y) > 25 ||
                std::abs(bx2 - m.x2) > 25 || std::abs(by2 - m.y2) > 25) {
                continue;
            }

            int ix1 = std::max(bx, m.x);
            int iy1 = std::max(by, m.y);
            int ix2 = std::min(bx2, m.x2);
            int iy2 = std::min(by2, m.y2);
            if (ix2 <= ix1 || iy2 <= iy1) continue;

            double inter = static_cast<double>(ix2 - ix1) * (iy2 - iy1);
            double uni = static_cast<double>(b_area) + m.area - inter;
            double iou = uni > 0.0 ? inter / uni : 0.0;
            double min_a = static_cast<double>(std::min(b_area, m.area));
            double contain = min_a > 0.0 ? inter / min_a : 0.0;

            int size_diff = std::abs(bw - m.w) + std::abs(bh - m.h);
            int min_dim = std::min({bw, bh, m.w, m.h});
            int max_size_diff = std::min(28, std::max(5, static_cast<int>(min_dim * 0.42)));

            const std::string& bt = b.type;
            const std::string& et = deduped[idx].type;
            bool has_grid = (bt == "grid_container" || bt == "grid_row" || et == "grid_container" || et == "grid_row");
            bool has_panel = (bt == "panel" || bt == "detected" || et == "panel" || et == "detected");
            if (has_grid && has_panel && size_diff > 10) continue;

            if (iou >= iou_thresh || (contain >= contain_thresh && size_diff <= max_size_diff)) {
                merged = true;
                auto& ex = deduped[idx];
                int nx = std::min(m.x, bx);
                int ny = std::min(m.y, by);
                int nx2 = std::max(m.x2, bx2);
                int ny2 = std::max(m.y2, by2);
                int nw = nx2 - nx;
                int nh = ny2 - ny;

                ex.x = nx;
                ex.y = ny;
                ex.w = nw;
                ex.h = nh;
                ex.area = nw * nh;
                if (type_priority(bt) > type_priority(et)) ex.type = bt;

                int ng_x = nx / kCellSize;
                int ng_y = ny / kCellSize;
                if (ng_x != m.gx || ng_y != m.gy) {
                    auto& old_bucket = grid[cell_key(m.gx, m.gy)];
                    std::erase(old_bucket, idx);
                    grid[cell_key(ng_x, ng_y)].push_back(idx);
                    m.gx = ng_x;
                    m.gy = ng_y;
                }
                m.x = nx; m.y = ny; m.x2 = nx2; m.y2 = ny2; m.w = nw; m.h = nh; m.area = nw * nh;
                break;
            }
        }

        if (!merged) {
            size_t idx = deduped.size();
            deduped.push_back(b);
            meta.push_back({bx, by, bx2, by2, bw, bh, b_area, b.is_client, gx, gy});
            grid[cell_key(gx, gy)].push_back(idx);
        }
    }

    return deduped;
}

std::vector<DetectedBox> CvDetector::cluster_slots_and_grids(std::vector<DetectedBox>& boxes) {
    std::vector<DetectedBox*> slots;
    for (auto& b : boxes) {
        if (b.type == "slot" ||
            (b.w >= 10 && b.w <= 180 && b.h >= 10 && b.h <= 180 &&
             (static_cast<double>(b.w) / b.h) >= 0.65 && (static_cast<double>(b.w) / b.h) <= 1.54 &&
             b.type != "item")) {
            if (b.type == "detected" || b.type.empty()) b.type = "slot";
            slots.push_back(&b);
        }
    }
    if (slots.size() < 2) return {};

    std::sort(slots.begin(), slots.end(), [](const DetectedBox* a, const DetectedBox* b) {
        return std::tie(a->y, a->x) < std::tie(b->y, b->x);
    });

    std::unordered_set<size_t> used_slots;
    std::vector<DetectedBox> rows;

    for (size_t i = 0; i < slots.size(); ++i) {
        if (used_slots.contains(i)) continue;
        std::vector<std::pair<DetectedBox*, size_t>> band = {{slots[i], i}};
        double tol_y = std::max(4.0, slots[i]->h * 0.25);

        for (size_t j = 0; j < slots.size(); ++j) {
            if (slots[j]->y - slots[i]->y > tol_y) break;
            if (j == i || used_slots.contains(j)) continue;
            if (std::abs(slots[i]->y - slots[j]->y) <= tol_y &&
                std::abs(slots[i]->h - slots[j]->h) <= tol_y) {
                band.push_back({slots[j], j});
            }
        }

        std::sort(band.begin(), band.end(), [](const auto& a, const auto& b) {
            return a.first->x < b.first->x;
        });

        auto emit_chain = [&](const std::vector<std::pair<DetectedBox*, size_t>>& chain) {
            if (chain.size() < 2) return;
            int rx = chain.front().first->x;
            int ry = chain.front().first->y;
            int rx2 = chain.back().first->x + chain.back().first->w;
            int ry2 = ry + chain.front().first->h;
            for (const auto& [s, idx] : chain) {
                ry = std::min(ry, s->y);
                ry2 = std::max(ry2, s->y + s->h);
                used_slots.insert(idx);
            }
            DetectedBox rb;
            rb.x = rx; rb.y = ry; rb.w = rx2 - rx; rb.h = ry2 - ry;
            rb.area = rb.w * rb.h; rb.extent = 0.96; rb.type = "grid_row";
            rows.push_back(std::move(rb));
        };

        std::vector<std::pair<DetectedBox*, size_t>> chain = {band.front()};
        for (size_t k = 1; k < band.size(); ++k) {
            auto* prev = chain.back().first;
            auto* curr = band[k].first;
            int gap = curr->x - (prev->x + prev->w);
            double avg_w = (prev->w + curr->w) * 0.5;
            if (gap >= -4 && gap <= std::max(14.0, avg_w * 0.65)) {
                chain.push_back(band[k]);
            } else {
                emit_chain(chain);
                chain = {band[k]};
            }
        }
        emit_chain(chain);
    }

    std::vector<DetectedBox> rows_sorted = rows;
    std::sort(rows_sorted.begin(), rows_sorted.end(), [](const DetectedBox& a, const DetectedBox& b) {
        return std::tie(a.x, a.y) < std::tie(b.x, b.y);
    });

    std::unordered_set<size_t> used_rows;
    std::vector<DetectedBox> grids;
    for (size_t i = 0; i < rows_sorted.size(); ++i) {
        if (used_rows.contains(i)) continue;
        std::vector<size_t> g_idx = {i};
        for (size_t j = 0; j < rows_sorted.size(); ++j) {
            if (j == i || used_rows.contains(j)) continue;
            const auto& prev_r = rows_sorted[g_idx.back()];
            const auto& r2 = rows_sorted[j];
            if (std::abs(prev_r.x - r2.x) <= std::max(14.0, prev_r.w * 0.08) &&
                std::abs(prev_r.w - r2.w) <= std::max(16.0, prev_r.w * 0.08)) {
                int v_gap = r2.y - (prev_r.y + prev_r.h);
                if (v_gap >= -6 && v_gap <= std::max(16.0, prev_r.h * 0.60)) {
                    g_idx.push_back(j);
                }
            }
        }
        if (g_idx.size() >= 2) {
            int gx = rows_sorted[g_idx.front()].x;
            int gy = rows_sorted[g_idx.front()].y;
            int gx2 = gx + rows_sorted[g_idx.front()].w;
            int gy2 = gy + rows_sorted[g_idx.front()].h;
            for (size_t idx : g_idx) {
                used_rows.insert(idx);
                const auto& r = rows_sorted[idx];
                gx = std::min(gx, r.x);
                gy = std::min(gy, r.y);
                gx2 = std::max(gx2, r.x + r.w);
                gy2 = std::max(gy2, r.y + r.h);
            }
            DetectedBox gb;
            gb.x = gx; gb.y = gy; gb.w = gx2 - gx; gb.h = gy2 - gy;
            gb.area = gb.w * gb.h; gb.extent = 0.98; gb.type = "grid_container";
            grids.push_back(std::move(gb));
        }
    }

    rows.insert(rows.end(), grids.begin(), grids.end());
    return rows;
}

std::vector<DetectedBox> CvDetector::cluster_adjacent_columns(const std::vector<DetectedBox>& boxes) {
    std::vector<const DetectedBox*> panels;
    for (const auto& b : boxes) {
        if (b.w >= 50 && b.h >= 100 &&
            (b.type == "panel" || b.type == "detected" || b.type == "grid_container")) {
            panels.push_back(&b);
        }
    }
    if (panels.size() < 2) return {};

    std::sort(panels.begin(), panels.end(), [](const DetectedBox* a, const DetectedBox* b) {
        return std::tie(a->y, a->x) < std::tie(b->y, b->x);
    });

    std::vector<DetectedBox> unions;
    for (size_t i = 0; i < panels.size(); ++i) {
        const auto* p1 = panels[i];
        int max_y_tol = std::max(12, static_cast<int>(p1->h * 0.10));
        for (size_t j = i + 1; j < panels.size(); ++j) {
            const auto* p2 = panels[j];
            int y_diff = p2->y - p1->y;
            if (y_diff > max_y_tol) break;
            int h_diff = std::abs(p1->h - p2->h);
            int min_h = std::min(p1->h, p2->h);
            if (y_diff <= std::max(12, static_cast<int>(min_h * 0.10)) &&
                h_diff <= std::max(16, static_cast<int>(min_h * 0.10))) {
                const auto* pl = (p1->x <= p2->x) ? p1 : p2;
                const auto* pr = (p1->x <= p2->x) ? p2 : p1;
                int gap = pr->x - (pl->x + pl->w);
                if (gap >= -6 && gap <= 40) {
                    int ux = pl->x;
                    int uy = std::min(pl->y, pr->y);
                    int uw = (pr->x + pr->w) - ux;
                    int uh = std::max(pl->y + pl->h, pr->y + pr->h) - uy;
                    int u_area = uw * uh;
                    if (u_area > std::max(p1->area, p2->area) * 1.25) {
                        DetectedBox u;
                        u.x = ux; u.y = uy; u.w = uw; u.h = uh;
                        u.area = u_area; u.extent = 0.98;
                        u.contrast = std::max(p1->contrast, p2->contrast);
                        u.type = "panel";
                        unions.push_back(std::move(u));
                    }
                }
            }
        }
    }
    return unions;
}

std::vector<DetectedBox> CvDetector::cluster_text_paragraphs(const std::vector<DetectedBox>& text_lines,
                                                             int min_lines,
                                                             bool multi_column) {
    if (static_cast<int>(text_lines.size()) < min_lines) return {};
    std::vector<DetectedBox> sorted = text_lines;
    std::sort(sorted.begin(), sorted.end(), [](const DetectedBox& a, const DetectedBox& b) {
        return std::tie(a.y, a.x) < std::tie(b.y, b.x);
    });

    if (!multi_column) {
        std::vector<DetectedBox> out;
        std::vector<DetectedBox> cur = {sorted.front()};
        for (size_t i = 1; i < sorted.size(); ++i) {
            const auto& line = sorted[i];
            const auto& last = cur.back();
            int vgap = line.y - (last.y + last.h);
            int max_vgap = std::max(18, std::min(26, static_cast<int>(last.h * 1.35)));
            int overlap_w = std::min(last.x + last.w, line.x + line.w) - std::max(last.x, line.x);
            bool aligned = (overlap_w > 0) || (std::abs(line.x - last.x) <= 36);
            if (vgap >= -6 && vgap <= max_vgap && aligned) {
                cur.push_back(line);
            } else {
                if (static_cast<int>(cur.size()) >= min_lines) out.push_back(make_text_block(cur));
                cur = {line};
            }
        }
        if (static_cast<int>(cur.size()) >= min_lines) out.push_back(make_text_block(cur));
        return out;
    }

    std::vector<std::vector<DetectedBox>> active_cols;
    std::vector<std::vector<DetectedBox>> finished;

    for (const auto& line : sorted) {
        int lx1 = line.x, lx2 = line.x + line.w, ly = line.y;
        std::vector<std::vector<DetectedBox>> still_active;
        for (auto& col : active_cols) {
            const auto& last = col.back();
            int vgap = ly - (last.y + last.h);
            int max_vgap = std::max(18, std::min(26, static_cast<int>(last.h * 1.35)));
            if (vgap > max_vgap) {
                if (static_cast<int>(col.size()) >= min_lines) finished.push_back(std::move(col));
                continue;
            }
            still_active.push_back(std::move(col));
        }
        active_cols = std::move(still_active);

        int best_idx = -1;
        int best_vgap = 1000000000;
        for (size_t idx = 0; idx < active_cols.size(); ++idx) {
            const auto& col = active_cols[idx];
            const auto& last = col.back();
            int vgap = ly - (last.y + last.h);
            if (vgap < -6) continue;
            int cx1 = col.front().x, cx2 = col.front().x + col.front().w;
            for (const auto& l : col) {
                cx1 = std::min(cx1, l.x);
                cx2 = std::max(cx2, l.x + l.w);
            }
            int cw = cx2 - cx1;
            int overlap_w = std::min(cx2, lx2) - std::max(cx1, lx1);
            int min_w = std::max(1, std::min(cw, line.w));
            int max_w = std::max(cw, line.w);
            bool width_ok = (max_w <= 2.8 * min_w) || (std::abs(lx1 - cx1) <= 28);
            bool horiz_ok = (overlap_w >= min_w * 0.22) || (std::abs(lx1 - cx1) <= 36);
            if (width_ok && horiz_ok && vgap < best_vgap) {
                best_vgap = vgap;
                best_idx = static_cast<int>(idx);
            }
        }
        if (best_idx >= 0) active_cols[static_cast<size_t>(best_idx)].push_back(line);
        else active_cols.push_back({line});
    }

    for (auto& col : active_cols) {
        if (static_cast<int>(col.size()) >= min_lines) finished.push_back(std::move(col));
    }

    std::vector<DetectedBox> out;
    out.reserve(finished.size());
    for (const auto& col : finished) out.push_back(make_text_block(col));
    return out;
}

CvDetectionResult CvDetector::detect(const PixelBuffer& img,
                                     const std::vector<ClientWindow>& clients,
                                     const nlohmann::json& cfg,
                                     const CvDetectionOptions& opts) {
    configure_opencv_threads_once();
    auto t0 = std::chrono::steady_clock::now();

    CvDetectionResult res;
    if (img.empty()) return res;

    int orig_w = img.width;
    int orig_h = img.height;
    res.screen_width = orig_w;
    res.screen_height = orig_h;
    res.preset = opts.preset_key.empty() ? cfg.value("activePreset", std::string("default")) : opts.preset_key;

    const auto det_cfg = (cfg.contains("detection") && cfg["detection"].is_object())
                             ? cfg["detection"]
                             : nlohmann::json::object();
    int min_area = std::max(1, det_cfg.value("minArea", 64));
    double max_area_ratio = det_cfg.value("maxAreaRatio", 0.98);
    double max_area = static_cast<double>(orig_w) * orig_h * max_area_ratio;
    double tiny_contrast_min = det_cfg.value("tinyContrastMin", 4.5);
    bool enable_panels = det_cfg.value("enablePanels", true);
    bool enable_grids = det_cfg.value("enableGrids", true);
    bool enable_win_content = det_cfg.value("enableWindowContent", true);
    bool enable_text = det_cfg.value("enableText", true);

    // Zero-copy BGRA Mat wrapping the SHM pixel buffer
    cv::Mat bgra(orig_h, orig_w, CV_8UC4, const_cast<uint8_t*>(img.data.data()), static_cast<size_t>(img.stride));
    cv::Mat gray;
    cv::cvtColor(bgra, gray, cv::COLOR_BGRA2GRAY);

    cv::Mat sat, sqsat;
    cv::integral(gray, sat, sqsat, CV_32S, CV_64F);

    // 1. CLAHE + Bilateral filter
    auto clahe = cv::createCLAHE(2.5, cv::Size(8, 8));
    cv::Mat cl, filtered;
    clahe->apply(gray, cl);
    cv::bilateralFilter(cl, filtered, 5, 25.0, 25.0);

    // 2. Multi-threshold Canny + Multi-scale closing
    cv::Mat edges_sharp, edges_dark, edges_raw;
    cv::Canny(filtered, edges_sharp, 28, 85);
    cv::Canny(filtered, edges_dark, 12, 45);
    cv::bitwise_or(edges_sharp, edges_dark, edges_raw);

    cv::Mat k_fine = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(2, 2));
    cv::Mat k_close = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(3, 3));
    cv::Mat closed_fine, closed_std, closed_edges;
    cv::morphologyEx(edges_raw, closed_fine, cv::MORPH_CLOSE, k_fine);
    cv::morphologyEx(edges_raw, closed_std, cv::MORPH_CLOSE, k_close);
    cv::bitwise_or(closed_fine, closed_std, closed_edges);

    cv::Mat edge_bin;
    cv::threshold(closed_edges, edge_bin, 0, 1, cv::THRESH_BINARY);
    cv::Mat edge_sat;
    cv::integral(edge_bin, edge_sat, CV_32S);

    // 3. Large-scale panel morph mask
    cv::Mat panel_mask;
    if (enable_panels) {
        cv::Mat k_panel = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(13, 13));
        cv::Mat closed_f, grad_f, pe_f, closed_g, grad_g, pe_g;
        cv::morphologyEx(filtered, closed_f, cv::MORPH_CLOSE, k_panel);
        cv::morphologyEx(closed_f, grad_f, cv::MORPH_GRADIENT, k_close);
        cv::threshold(grad_f, pe_f, 8, 255, cv::THRESH_BINARY);

        cv::morphologyEx(gray, closed_g, cv::MORPH_CLOSE, k_panel);
        cv::morphologyEx(closed_g, grad_g, cv::MORPH_GRADIENT, k_close);
        cv::threshold(grad_g, pe_g, 12, 255, cv::THRESH_BINARY);
        cv::bitwise_or(pe_f, pe_g, panel_mask);
    }

    std::vector<DetectedBox> raw_boxes;
    std::vector<DetectedBox> client_boxes;

    // 4. Pre-seed Hyprland client windows & visible layer-shell popouts
    double mon_scale = (opts.monitor_scale > 0.0) ? opts.monitor_scale : 1.0;
    for (const auto& c : clients) {
        if (c.hidden || !c.mapped) continue;
        if (opts.active_workspace_id != 0 && !c.pinned && c.workspace_id != opts.active_workspace_id) {
            continue;
        }
        int cx = c.x - opts.monitor_x;
        int cy = c.y - opts.monitor_y;
        if (c.w < 20 || c.h < 20) continue;

        int px = static_cast<int>(std::lround(cx * mon_scale));
        int py = static_cast<int>(std::lround(cy * mon_scale));
        int pw = static_cast<int>(std::lround(c.w * mon_scale));
        int ph = static_cast<int>(std::lround(c.h * mon_scale));

        int cx1 = std::clamp(px, 0, orig_w);
        int cy1 = std::clamp(py, 0, orig_h);
        int cx2 = std::clamp(px + pw, 0, orig_w);
        int cy2 = std::clamp(py + ph, 0, orig_h);
        int cw = cx2 - cx1;
        int ch = cy2 - cy1;
        if (cw < 20 || ch < 20) continue;

        std::string cls_low = to_lower_copy(c.wm_class);
        if (cls_low.find("bongocat") != std::string::npos ||
            cls_low == "caelestia-drawers" || cls_low == "caelestia-background" ||
            cls_low == "caelestia-border-exclusion" || cls_low == "awww-daemon" ||
            (c.floating && c.pinned && cw >= orig_w * 0.92 && ch >= orig_h * 0.92)) {
            continue;
        }

        DetectedBox wb;
        wb.x = cx1; wb.y = cy1; wb.w = cw; wb.h = ch;
        wb.area = cw * ch;
        wb.extent = 1.0;
        wb.contrast = 60.0;
        wb.type = c.floating ? "floating_window" : "window";
        wb.floating = c.floating;
        wb.pinned = c.pinned;
        wb.is_layer = c.is_layer;
        wb.focus_history_id = c.focus_history_id;
        wb.title = c.title;
        wb.wm_class = c.wm_class;
        wb.is_client = true;
        wb.source = "client";
        raw_boxes.push_back(wb);
        client_boxes.push_back(std::move(wb));
    }

    // 5. Find contours on sharp edges + panel mask
    auto run_contour_pass = [&](bool is_panel_morph, const cv::Mat& mask) {
        std::vector<std::vector<cv::Point>> contours;
        cv::findContours(mask, contours, cv::RETR_CCOMP, cv::CHAIN_APPROX_SIMPLE);
        std::vector<cv::Point> approx;

        for (const auto& cnt : contours) {
            cv::Rect r = cv::boundingRect(cnt);
            if (is_panel_morph) {
                if (r.width < 120 || r.height < 50) continue;
            } else if (r.width < 12 || r.height < 12) {
                continue;
            }
            int box_area = r.width * r.height;
            if (box_area < min_area || box_area > max_area) continue;
            if ((r.height <= 4 && r.width > 40) || (r.width <= 4 && r.height > 40)) continue;

            double area = cv::contourArea(cnt);
            double extent = area / static_cast<double>(box_area);
            double min_extent = (r.width >= 160 && r.height >= 50) ? 0.38 : (box_area < 450 ? 0.42 : 0.48);
            if (extent < min_extent) continue;

            double peri = cv::arcLength(cnt, true);
            cv::approxPolyDP(cnt, approx, 0.02 * peri, true);
            int nv = static_cast<int>(approx.size());
            int max_vertices = (box_area < 500) ? 24 : 28;
            if (nv > max_vertices) continue;

            bool is_big_panel = (r.width >= 220 && r.height >= 140);
            std::optional<double> avg_edge;
            std::optional<double> in_ed;

            if (!is_panel_morph && !is_big_panel) {
                if (nv < 4) continue;
                double t = sat_mean_i32(edge_sat, r.x, r.y, r.x + r.width, std::min(r.y + r.height, r.y + 2));
                double b = sat_mean_i32(edge_sat, r.x, std::max(r.y, r.y + r.height - 2), r.x + r.width, r.y + r.height);
                double l = sat_mean_i32(edge_sat, r.x, r.y, std::min(r.x + r.width, r.x + 2), r.y + r.height);
                double rt = sat_mean_i32(edge_sat, std::max(r.x, r.x + r.width - 2), r.y, r.x + r.width, r.y + r.height);
                std::array<double, 4> sides = {t, b, l, rt};
                std::sort(sides.begin(), sides.end());
                double ae = (t + b + l + rt) * 0.25;
                double ie = (r.width > 8 && r.height > 8)
                                ? sat_mean_i32(edge_sat, r.x + 3, r.y + 3, r.x + r.width - 3, r.y + r.height - 3)
                                : 0.0;
                avg_edge = ae;
                in_ed = ie;

                bool is_clean_rounded = (sides[0] >= 0.25 && ae >= 0.32 && ie <= 0.20 && extent >= 0.60);
                if (!is_clean_rounded) {
                    if (sides[0] < 0.22 && sides[1] < 0.38) continue;
                    if (ae < 0.42) continue;
                }
                if (r.width < 120 && r.height < 48 && ie > 0.60) continue;
            }

            auto [valid, contrast] = is_valid_border(gray, sat, r.x, r.y, r.width, r.height);
            if (!valid) continue;
            if (!is_panel_morph && r.width < 48 && r.height < 48 && contrast < tiny_contrast_min) continue;

            std::string elem_type = "detected";
            if (is_panel_morph) {
                elem_type = is_big_panel ? "panel" : "detected";
            } else if (is_big_panel) {
                elem_type = "panel";
            } else if (r.width >= 10 && r.width <= 180 && r.height >= 10 && r.height <= 180 &&
                       (static_cast<double>(r.width) / r.height) >= 0.65 &&
                       (static_cast<double>(r.width) / r.height) <= 1.54) {
                elem_type = "slot";
            } else if (r.width >= 20 && r.width <= 800 && r.height >= 12 && r.height <= 64) {
                elem_type = (r.width > 260) ? "input" : "button";
            }

            DetectedBox entry;
            entry.x = r.x; entry.y = r.y; entry.w = r.width; entry.h = r.height;
            entry.area = box_area;
            entry.extent = extent;
            entry.contrast = contrast;
            entry.type = std::move(elem_type);
            entry.edge_score = avg_edge;
            entry.interior_edge = in_ed;
            raw_boxes.push_back(std::move(entry));
        }
    };

    run_contour_pass(false, closed_edges);
    if (enable_panels) run_contour_pass(true, panel_mask);

    // Suppress periodic mesh / tile artifacts
    std::unordered_map<int64_t, int> size_bins;
    auto bin_key = [](int w, int h) -> int64_t {
        return (static_cast<int64_t>(w / 4) << 32) ^ static_cast<uint32_t>(h / 4);
    };
    for (const auto& b : raw_boxes) size_bins[bin_key(b.w, b.h)]++;

    std::vector<DetectedBox> filtered_boxes;
    filtered_boxes.reserve(raw_boxes.size());
    for (auto& b : raw_boxes) {
        if (size_bins[bin_key(b.w, b.h)] > 14 && b.contrast < 22.0) continue;
        filtered_boxes.push_back(std::move(b));
    }

    auto deduped_raw = deduplicate_boxes(filtered_boxes, 0.72, 0.88);

    // Nested items inside slots
    std::vector<size_t> slot_indices;
    for (size_t i = 0; i < deduped_raw.size(); ++i) {
        if (deduped_raw[i].type == "slot") slot_indices.push_back(i);
    }
    if (!slot_indices.empty()) {
        for (size_t i = 0; i < deduped_raw.size(); ++i) {
            auto& b = deduped_raw[i];
            int bx1 = b.x, by1 = b.y, bx2 = b.x + b.w, by2 = b.y + b.h;
            double thresh_a = b.area * 1.3;
            for (size_t si : slot_indices) {
                if (si == i) continue;
                const auto& s = deduped_raw[si];
                if (s.area > thresh_a &&
                    bx1 >= s.x - 2 && by1 >= s.y - 2 &&
                    bx2 <= s.x + s.w + 2 && by2 <= s.y + s.h + 2) {
                    b.type = "item";
                    break;
                }
            }
        }
    }

    auto synthesized = enable_grids ? cluster_slots_and_grids(deduped_raw) : std::vector<DetectedBox>{};
    auto col_unions = enable_panels ? cluster_adjacent_columns(deduped_raw) : std::vector<DetectedBox>{};
    auto win_content = enable_win_content ? detect_window_content_areas(gray, client_boxes) : std::vector<DetectedBox>{};
    auto text_regions = enable_text ? detect_text_regions(gray, sat, sqsat, cl, orig_w, orig_h, det_cfg)
                                    : std::vector<DetectedBox>{};

    std::vector<DetectedBox> all_boxes;
    all_boxes.reserve(deduped_raw.size() + synthesized.size() + col_unions.size() +
                      win_content.size() + text_regions.size());
    auto append_vec = [&](std::vector<DetectedBox>& v) {
        all_boxes.insert(all_boxes.end(), std::make_move_iterator(v.begin()), std::make_move_iterator(v.end()));
    };
    append_vec(deduped_raw);
    append_vec(synthesized);
    append_vec(col_unions);
    append_vec(win_content);
    append_vec(text_regions);

    auto final_deduped = deduplicate_boxes(all_boxes, 0.80, 0.90);

    std::vector<DetectedBox> clamped;
    clamped.reserve(final_deduped.size());
    for (auto& b : final_deduped) {
        int x1 = std::clamp(b.x, 0, orig_w);
        int y1 = std::clamp(b.y, 0, orig_h);
        int x2 = std::clamp(b.x + b.w, 0, orig_w);
        int y2 = std::clamp(b.y + b.h, 0, orig_h);
        int bw = x2 - x1;
        int bh = y2 - y1;
        if (bw < 8 || bh < 8) continue;
        b.x = x1; b.y = y1; b.w = bw; b.h = bh; b.area = bw * bh;
        clamped.push_back(std::move(b));
    }

    auto rated = RatingEngine::rate_and_filter(clamped, res.preset, cfg, opts.explicit_rating_profile);

    std::sort(rated.begin(), rated.end(), [](const DetectedBox& a, const DetectedBox& b) {
        return a.area < b.area;
    });
    for (size_t i = 0; i < rated.size(); ++i) {
        auto& box = rated[i];
        box.id = static_cast<int>(i);
        int bx1 = box.x, by1 = box.y, bx2 = box.x + box.w, by2 = box.y + box.h;
        double min_parent = box.area * 1.05;
        int depth = 0;
        for (size_t j = i + 1; j < rated.size(); ++j) {
            const auto& p = rated[j];
            if (p.area > min_parent &&
                bx1 >= p.x - 4 && by1 >= p.y - 4 &&
                bx2 <= p.x + p.w + 4 && by2 <= p.y + p.h + 4) {
                depth++;
            }
        }
        box.depth = depth;
    }

    std::sort(rated.begin(), rated.end(), [](const DetectedBox& a, const DetectedBox& b) {
        return a.area > b.area;
    });

    auto t1 = std::chrono::steady_clock::now();
    res.elapsed_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
    res.boxes = std::move(rated);
    return res;
}

}  // namespace hss
