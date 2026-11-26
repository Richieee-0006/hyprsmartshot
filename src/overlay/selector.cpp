#include "overlay/selector.hpp"

#include <algorithm>
#include <cmath>

namespace hss {

void SmartSelector::init(int logical_w, int logical_h, double monitor_scale,
                         const std::string& mode, const std::string& preset_key,
                         const nlohmann::json& cfg) {
    logical_w_ = std::max(1, logical_w);
    logical_h_ = std::max(1, logical_h);
    scale_ = (monitor_scale > 0.0) ? monitor_scale : 1.0;
    mode_ = mode.empty() ? "universal" : mode;
    active_preset_ = preset_key.empty() ? "default" : preset_key;
    cfg_ = cfg;
    sort_by_rating_ = !(cfg.contains("ui") && cfg["ui"].is_object() &&
                        cfg["ui"].value("sortByRating", true) == false);

    cv_boxes_.clear();
    ai_boxes_.clear();
    hierarchy_.clear();
    hierarchy_idx_ = 0;
    cv_ready_ = false;
    is_confirmed_ = false;
    is_dragging_ = false;
    press_active_ = false;
    active_handle_ = ResizeHandle::None;
    cursor_x_ = logical_w_ * 0.5;
    cursor_y_ = logical_h_ * 0.5;

    if (mode_ == "screen") {
        select_fullscreen();
    } else {
        sel_x_ = 0; sel_y_ = 0; sel_w_ = logical_w_; sel_h_ = logical_h_;
    }
}

void SmartSelector::set_mode(const std::string& mode) {
    mode_ = mode;
    if (mode_ == "screen") {
        select_fullscreen();
    } else {
        is_confirmed_ = false;
        update_hover_candidates(cursor_x_, cursor_y_);
    }
}

void SmartSelector::set_preset(const std::string& preset_key) {
    active_preset_ = preset_key.empty() ? "default" : preset_key;
    if (!is_confirmed_) {
        update_hover_candidates(cursor_x_, cursor_y_);
    }
}

void SmartSelector::set_cv_boxes(const std::vector<DetectedBox>& phys_boxes) {
    cv_boxes_.clear();
    cv_boxes_.reserve(phys_boxes.size());
    for (const auto& b : phys_boxes) {
        CandidateBox cb;
        cb.x = b.x / scale_;
        cb.y = b.y / scale_;
        cb.w = b.w / scale_;
        cb.h = b.h / scale_;
        cb.area = cb.w * cb.h;
        cb.type = b.type;
        cb.label = b.label.empty() ? b.title : b.label;
        cb.source = b.is_client ? "client" : b.source;
        cb.is_client = b.is_client;
        cb.floating = b.floating;
        cb.is_layer = b.is_layer;
        cb.focus_history_id = b.focus_history_id;
        cb.confidence = b.confidence;
        cb.score = b.score;
        cv_boxes_.push_back(std::move(cb));
    }
    cv_ready_ = true;
    if (!is_confirmed_ && !is_dragging_ && mode_ != "screen") {
        update_hover_candidates(cursor_x_, cursor_y_);
    }
}

void SmartSelector::set_ai_boxes(const std::vector<DetectedBox>& phys_boxes) {
    ai_boxes_.clear();
    ai_boxes_.reserve(phys_boxes.size());
    for (const auto& b : phys_boxes) {
        CandidateBox cb;
        cb.x = b.x / scale_;
        cb.y = b.y / scale_;
        cb.w = b.w / scale_;
        cb.h = b.h / scale_;
        cb.area = cb.w * cb.h;
        cb.type = b.type;
        cb.label = b.label;
        cb.source = "ai";
        cb.confidence = b.confidence;
        cb.score = b.score;
        ai_boxes_.push_back(std::move(cb));
    }
    if (!is_confirmed_ && !is_dragging_ && mode_ != "screen") {
        update_hover_candidates(cursor_x_, cursor_y_);
    }
}

bool SmartSelector::preset_allows_box(const CandidateBox& b) const {
    if (b.is_client || b.source == "ai") return true;
    std::string filter = "all";
    if (cfg_.contains("presets") && cfg_["presets"].is_object() &&
        cfg_["presets"].contains(active_preset_) && cfg_["presets"][active_preset_].is_object()) {
        filter = cfg_["presets"][active_preset_].value("filter", std::string("all"));
    }
    if (filter == "window") {
        return b.type == "window" || b.type == "floating_window" || b.type == "panel" || b.type == "text_block";
    }
    if (filter == "content") {
        return b.type != "slot" && b.type != "item" && b.type != "grid_row" && b.type != "grid_container";
    }
    return true;
}

void SmartSelector::apply_preset_box(const CandidateBox& b) {
    double ox = 0, oy = 0, inset = 0;
    if (cfg_.contains("presets") && cfg_["presets"].is_object() &&
        cfg_["presets"].contains(active_preset_) && cfg_["presets"][active_preset_].is_object()) {
        const auto& p = cfg_["presets"][active_preset_];
        ox = p.value("offsetX", 0.0);
        oy = p.value("offsetY", 0.0);
        inset = p.value("inset", 0.0);
    }
    sel_x_ = b.x + ox + inset;
    sel_y_ = b.y + oy + inset;
    sel_w_ = std::max(8.0, b.w - inset * 2.0);
    sel_h_ = std::max(8.0, b.h - inset * 2.0);
    clamp_selection();
}

void SmartSelector::clamp_selection() {
    sel_x_ = std::clamp(sel_x_, 0.0, static_cast<double>(logical_w_ - 2));
    sel_y_ = std::clamp(sel_y_, 0.0, static_cast<double>(logical_h_ - 2));
    sel_w_ = std::clamp(sel_w_, 2.0, logical_w_ - sel_x_);
    sel_h_ = std::clamp(sel_h_, 2.0, logical_h_ - sel_y_);
}

void SmartSelector::select_fullscreen() {
    sel_x_ = 0;
    sel_y_ = 0;
    sel_w_ = logical_w_;
    sel_h_ = logical_h_;
    is_confirmed_ = true;
    hierarchy_.clear();
    CandidateBox screen_box;
    screen_box.x = 0; screen_box.y = 0;
    screen_box.w = logical_w_; screen_box.h = logical_h_;
    screen_box.area = sel_w_ * sel_h_;
    screen_box.type = "screen";
    screen_box.source = "screen";
    screen_box.confidence = 1.0;
    screen_box.score = 100;
    hierarchy_.push_back(screen_box);
    hierarchy_idx_ = 0;
}

void SmartSelector::update_hover_candidates(double mx, double my) {
    hierarchy_.clear();
    hierarchy_idx_ = 0;

    if (mode_ == "screen") {
        select_fullscreen();
        return;
    }

    // 1. Identify topmost floating / layer-shell popout window under cursor
    const CandidateBox* top_floating = nullptr;
    for (const auto& b : cv_boxes_) {
        if (!b.is_client || !b.floating) continue;
        if (mx >= b.x && mx <= b.x + b.w && my >= b.y && my <= b.y + b.h) {
            if (!top_floating ||
                (b.is_layer && !top_floating->is_layer) ||
                (b.is_layer == top_floating->is_layer && b.focus_history_id < top_floating->focus_history_id)) {
                top_floating = &b;
            }
        }
    }

    auto inside_floating = [&](const CandidateBox& b) -> bool {
        if (!top_floating) return true;
        return b.x >= top_floating->x - 6.0 && b.y >= top_floating->y - 6.0 &&
               (b.x + b.w) <= (top_floating->x + top_floating->w + 6.0) &&
               (b.y + b.h) <= (top_floating->y + top_floating->h + 6.0);
    };

    // 2. Gather matching CV & client boxes (mode=="window" restricts to windows only)
    for (const auto& b : cv_boxes_) {
        if (mode_ == "window" && !b.is_client) continue;
        if (!preset_allows_box(b)) continue;
        if (mx < b.x || mx > b.x + b.w || my < b.y || my > b.y + b.h) continue;
        if (top_floating && &b != top_floating && !inside_floating(b)) continue;
        hierarchy_.push_back(b);
    }

    // 3. Gather matching AI boxes
    if (mode_ != "window") {
        for (const auto& ab : ai_boxes_) {
            if (mx < ab.x || mx > ab.x + ab.w || my < ab.y || my > ab.y + ab.h) continue;
            if (!inside_floating(ab)) continue;
            hierarchy_.push_back(ab);
        }
    }

    // 4. Add fullscreen fallback at end of hierarchy
    CandidateBox screen_box;
    screen_box.x = 0; screen_box.y = 0;
    screen_box.w = logical_w_; screen_box.h = logical_h_;
    screen_box.area = static_cast<double>(logical_w_) * logical_h_;
    screen_box.type = "screen";
    screen_box.source = "screen";
    screen_box.confidence = 1.0;
    screen_box.score = 100;
    hierarchy_.push_back(screen_box);

    // 5. Sort innermost-first (smallest area first, AI/higher confidence breaks near-ties)
    std::sort(hierarchy_.begin(), hierarchy_.end(), [&](const CandidateBox& a, const CandidateBox& b) {
        if (a.source == "screen" && b.source != "screen") return false;
        if (b.source == "screen" && a.source != "screen") return true;
        double ratio = (b.area > 0.0) ? (a.area / b.area) : 1.0;
        if (sort_by_rating_ && ratio >= 0.85 && ratio <= 1.18) {
            if (a.source == "ai" && b.source != "ai") return true;
            if (b.source == "ai" && a.source != "ai") return false;
            if (std::abs(a.confidence - b.confidence) > 0.03) return a.confidence > b.confidence;
        }
        return a.area < b.area;
    });

    // Deduplicate virtually identical stacked candidates
    std::vector<CandidateBox> dedup;
    dedup.reserve(hierarchy_.size());
    for (const auto& c : hierarchy_) {
        bool dup = false;
        for (const auto& e : dedup) {
            if (std::abs(c.x - e.x) <= 4.0 && std::abs(c.y - e.y) <= 4.0 &&
                std::abs(c.w - e.w) <= 6.0 && std::abs(c.h - e.h) <= 6.0) {
                dup = true;
                break;
            }
        }
        if (!dup) dedup.push_back(c);
    }
    hierarchy_ = std::move(dedup);

    if (!hierarchy_.empty()) {
        apply_preset_box(hierarchy_[0]);
    }
}

double SmartSelector::magnetic_snap(double val, bool horizontal, double threshold) const {
    double best = val;
    double best_dist = threshold + 1.0;
    auto check = [&](double edge) {
        double d = std::abs(val - edge);
        if (d < best_dist) {
            best_dist = d;
            best = edge;
        }
    };
    for (const auto& b : cv_boxes_) {
        if (horizontal) {
            check(b.x);
            check(b.x + b.w);
        } else {
            check(b.y);
            check(b.y + b.h);
        }
    }
    return best;
}

ResizeHandle SmartSelector::hit_test_handle(double mx, double my) const {
    if (!is_confirmed_ || !has_selection()) return ResizeHandle::None;
    constexpr double kTol = 10.0;
    double x1 = sel_x_, y1 = sel_y_, x2 = sel_x_ + sel_w_, y2 = sel_y_ + sel_h_;
    double cx = (x1 + x2) * 0.5, cy = (y1 + y2) * 0.5;

    auto near_pt = [&](double px, double py) {
        return std::abs(mx - px) <= kTol && std::abs(my - py) <= kTol;
    };
    if (near_pt(x1, y1)) return ResizeHandle::NW;
    if (near_pt(x2, y1)) return ResizeHandle::NE;
    if (near_pt(x1, y2)) return ResizeHandle::SW;
    if (near_pt(x2, y2)) return ResizeHandle::SE;
    if (near_pt(cx, y1)) return ResizeHandle::N;
    if (near_pt(cx, y2)) return ResizeHandle::S;
    if (near_pt(x1, cy)) return ResizeHandle::W;
    if (near_pt(x2, cy)) return ResizeHandle::E;
    if (mx >= x1 && mx <= x2 && my >= y1 && my <= y2) return ResizeHandle::Move;
    return ResizeHandle::None;
}

void SmartSelector::on_pointer_move(double mx, double my) {
    cursor_x_ = std::clamp(mx, 0.0, static_cast<double>(logical_w_));
    cursor_y_ = std::clamp(my, 0.0, static_cast<double>(logical_h_));

    if (active_handle_ != ResizeHandle::None) {
        double dx = cursor_x_ - press_x_;
        double dy = cursor_y_ - press_y_;
        double nx = orig_x_, ny = orig_y_, nw = orig_w_, nh = orig_h_;
        if (active_handle_ == ResizeHandle::Move) {
            nx = std::clamp(orig_x_ + dx, 0.0, logical_w_ - orig_w_);
            ny = std::clamp(orig_y_ + dy, 0.0, logical_h_ - orig_h_);
        } else {
            double x1 = orig_x_, y1 = orig_y_, x2 = orig_x_ + orig_w_, y2 = orig_y_ + orig_h_;
            if (active_handle_ == ResizeHandle::NW || active_handle_ == ResizeHandle::W || active_handle_ == ResizeHandle::SW)
                x1 = std::min(x2 - 8.0, magnetic_snap(orig_x_ + dx, true, 6.0));
            if (active_handle_ == ResizeHandle::NE || active_handle_ == ResizeHandle::E || active_handle_ == ResizeHandle::SE)
                x2 = std::max(x1 + 8.0, magnetic_snap(orig_x_ + orig_w_ + dx, true, 6.0));
            if (active_handle_ == ResizeHandle::NW || active_handle_ == ResizeHandle::N || active_handle_ == ResizeHandle::NE)
                y1 = std::min(y2 - 8.0, magnetic_snap(orig_y_ + dy, false, 6.0));
            if (active_handle_ == ResizeHandle::SW || active_handle_ == ResizeHandle::S || active_handle_ == ResizeHandle::SE)
                y2 = std::max(y1 + 8.0, magnetic_snap(orig_y_ + orig_h_ + dy, false, 6.0));
            nx = x1; ny = y1; nw = x2 - x1; nh = y2 - y1;
        }
        sel_x_ = nx; sel_y_ = ny; sel_w_ = nw; sel_h_ = nh;
        clamp_selection();
        return;
    }

    if (press_active_) {
        double dist = std::hypot(cursor_x_ - press_x_, cursor_y_ - press_y_);
        if (dist >= 6.0) is_dragging_ = true;
        if (is_dragging_) {
            double sx = magnetic_snap(cursor_x_, true, 7.0);
            double sy = magnetic_snap(cursor_y_, false, 7.0);
            sel_x_ = std::min(press_x_, sx);
            sel_y_ = std::min(press_y_, sy);
            sel_w_ = std::max(4.0, std::abs(sx - press_x_));
            sel_h_ = std::max(4.0, std::abs(sy - press_y_));
            clamp_selection();
            return;
        }
    }

    if (!is_confirmed_) {
        update_hover_candidates(cursor_x_, cursor_y_);
    }
}

void SmartSelector::on_pointer_press(double mx, double my) {
    cursor_x_ = mx;
    cursor_y_ = my;
    press_x_ = mx;
    press_y_ = my;

    if (is_confirmed_) {
        ResizeHandle h = hit_test_handle(mx, my);
        if (h != ResizeHandle::None) {
            active_handle_ = h;
            orig_x_ = sel_x_; orig_y_ = sel_y_; orig_w_ = sel_w_; orig_h_ = sel_h_;
            return;
        }
        // Clicking outside confirmed selection starts a new selection / returns to hover
        is_confirmed_ = false;
        update_hover_candidates(mx, my);
    }

    press_active_ = true;
    is_dragging_ = false;
}

void SmartSelector::on_pointer_release(double mx, double my) {
    cursor_x_ = mx;
    cursor_y_ = my;
    if (active_handle_ != ResizeHandle::None) {
        active_handle_ = ResizeHandle::None;
        return;
    }
    if (press_active_) {
        press_active_ = false;
        if (is_dragging_) {
            is_dragging_ = false;
            hierarchy_.clear();
            is_confirmed_ = (sel_w_ >= 4.0 && sel_h_ >= 4.0);
        } else {
            if (!has_selection()) update_hover_candidates(mx, my);
            is_confirmed_ = has_selection();
        }
    }
}

void SmartSelector::on_wheel(int direction) {
    if (!is_confirmed_) cycle_hierarchy(direction);
}

void SmartSelector::cycle_hierarchy(int direction) {
    if (hierarchy_.empty()) return;
    int n = static_cast<int>(hierarchy_.size());
    hierarchy_idx_ = (hierarchy_idx_ + (direction > 0 ? 1 : -1) + n) % n;
    apply_preset_box(hierarchy_[static_cast<size_t>(hierarchy_idx_)]);
}

void SmartSelector::nudge(double dx, double dy) {
    sel_x_ += dx;
    sel_y_ += dy;
    clamp_selection();
}

void SmartSelector::resize(double dw, double dh) {
    sel_w_ = std::max(8.0, sel_w_ + dw);
    sel_h_ = std::max(8.0, sel_h_ + dh);
    clamp_selection();
}

void SmartSelector::clear_confirmation() {
    is_confirmed_ = false;
    active_handle_ = ResizeHandle::None;
    press_active_ = false;
    is_dragging_ = false;
    if (mode_ == "screen") mode_ = "universal";
    update_hover_candidates(cursor_x_, cursor_y_);
}

const CandidateBox* SmartSelector::selected_candidate() const {
    if (hierarchy_idx_ >= 0 && hierarchy_idx_ < static_cast<int>(hierarchy_.size())) {
        return &hierarchy_[static_cast<size_t>(hierarchy_idx_)];
    }
    return nullptr;
}

}  // namespace hss
