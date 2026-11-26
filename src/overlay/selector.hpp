#pragma once

#include "core/hyprland_ipc.hpp"
#include "vision/rating.hpp"

#include <optional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace hss {

enum class ResizeHandle {
    None, NW, N, NE, E, SE, S, SW, W, Move
};

struct CandidateBox {
    double x = 0;
    double y = 0;
    double w = 0;
    double h = 0;
    double area = 0;
    std::string type = "detected";
    std::string label;
    std::string source = "cv";  // "cv" | "ai" | "client" | "screen"
    bool is_client = false;
    bool floating = false;
    bool is_layer = false;
    int focus_history_id = 999;
    double confidence = 0.80;
    int score = 80;
};

class SmartSelector {
public:
    void init(int logical_w, int logical_h, double monitor_scale,
              const std::string& mode, const std::string& preset_key,
              const nlohmann::json& cfg);

    void set_mode(const std::string& mode);
    void set_preset(const std::string& preset_key);
    void set_cv_boxes(const std::vector<DetectedBox>& phys_boxes);
    void set_ai_boxes(const std::vector<DetectedBox>& phys_boxes);

    // Pointer interactions
    void on_pointer_move(double mx, double my);
    void on_pointer_press(double mx, double my);
    void on_pointer_release(double mx, double my);
    void on_wheel(int direction);  // +1 up / -1 down

    // Keyboard adjustments
    void cycle_hierarchy(int direction);
    void nudge(double dx, double dy);
    void resize(double dw, double dh);
    void clear_confirmation();
    void select_fullscreen();

    ResizeHandle hit_test_handle(double mx, double my) const;

    // Accessors
    const std::string& mode() const { return mode_; }
    const std::string& active_preset() const { return active_preset_; }
    bool is_confirmed() const { return is_confirmed_; }
    bool is_dragging() const { return is_dragging_; }
    bool is_resizing() const { return active_handle_ != ResizeHandle::None; }
    bool has_selection() const { return sel_w_ >= 2.0 && sel_h_ >= 2.0; }

    double sel_x() const { return sel_x_; }
    double sel_y() const { return sel_y_; }
    double sel_w() const { return sel_w_; }
    double sel_h() const { return sel_h_; }
    double cursor_x() const { return cursor_x_; }
    double cursor_y() const { return cursor_y_; }
    int hierarchy_index() const { return hierarchy_idx_; }
    const std::vector<CandidateBox>& hierarchy() const { return hierarchy_; }
    const CandidateBox* selected_candidate() const;

    bool cv_ready() const { return cv_ready_; }
    bool ai_active() const { return !ai_boxes_.empty(); }

private:
    void update_hover_candidates(double mx, double my);
    bool preset_allows_box(const CandidateBox& b) const;
    void apply_preset_box(const CandidateBox& b);
    double magnetic_snap(double val, bool horizontal, double threshold = 8.0) const;
    void clamp_selection();

    int logical_w_ = 1920;
    int logical_h_ = 1080;
    double scale_ = 1.0;
    std::string mode_ = "universal";
    std::string active_preset_ = "default";
    nlohmann::json cfg_;
    bool sort_by_rating_ = true;

    std::vector<CandidateBox> cv_boxes_;
    std::vector<CandidateBox> ai_boxes_;
    std::vector<CandidateBox> hierarchy_;
    int hierarchy_idx_ = 0;
    bool cv_ready_ = false;

    bool is_confirmed_ = false;
    bool is_dragging_ = false;
    bool press_active_ = false;
    double press_x_ = 0;
    double press_y_ = 0;
    ResizeHandle active_handle_ = ResizeHandle::None;
    double orig_x_ = 0, orig_y_ = 0, orig_w_ = 0, orig_h_ = 0;

    double sel_x_ = 0, sel_y_ = 0, sel_w_ = 0, sel_h_ = 0;
    double cursor_x_ = 0, cursor_y_ = 0;
};

}  // namespace hss
