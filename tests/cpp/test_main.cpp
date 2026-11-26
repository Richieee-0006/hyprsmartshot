#include "core/config.hpp"
#include "core/hyprland_ipc.hpp"
#include "core/i18n.hpp"
#include "core/image_ops.hpp"
#include "overlay/selector.hpp"
#include "vision/ai_client.hpp"
#include "vision/detect_ui.hpp"
#include "vision/rating.hpp"
#include "wayland/pin_window.hpp"

#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <sys/wait.h>
#include <unistd.h>

namespace fs = std::filesystem;

static int g_passed = 0;

#define CHECK(expr)                                                                             \
    do {                                                                                        \
        if (!(expr)) {                                                                          \
            std::cerr << "FAIL [" << __func__ << ":" << __LINE__ << "] " #expr << "\n";         \
            std::exit(1);                                                                       \
        }                                                                                       \
    } while (0)

struct TempDir {
    fs::path path;
    TempDir() {
        std::string tmpl = "/tmp/hss_test_XXXXXX";
        char* p = ::mkdtemp(tmpl.data());
        CHECK(p != nullptr);
        path = p;
    }
    ~TempDir() {
        std::error_code ec;
        fs::remove_all(path, ec);
    }
};

static std::pair<int, std::string> run_cmd_capture(const std::vector<std::string>& argv) {
    int pfd[2];
    CHECK(::pipe(pfd) == 0);
    pid_t pid = ::fork();
    CHECK(pid >= 0);
    if (pid == 0) {
        ::dup2(pfd[1], STDOUT_FILENO);
        ::dup2(pfd[1], STDERR_FILENO);
        ::close(pfd[0]);
        ::close(pfd[1]);
        std::vector<char*> cargv;
        for (const auto& a : argv) cargv.push_back(const_cast<char*>(a.c_str()));
        cargv.push_back(nullptr);
        ::execvp(cargv[0], cargv.data());
        ::_exit(127);
    }
    ::close(pfd[1]);
    std::string out;
    char buf[1024];
    ssize_t n;
    while ((n = ::read(pfd[0], buf, sizeof(buf))) > 0) out.append(buf, static_cast<size_t>(n));
    ::close(pfd[0]);
    int st = 0;
    ::waitpid(pid, &st, 0);
    return {WIFEXITED(st) ? WEXITSTATUS(st) : -1, out};
}

static hss::PixelBuffer make_solid_bgra(int w, int h, uint8_t b, uint8_t g, uint8_t r) {
    hss::PixelBuffer buf;
    buf.width = w;
    buf.height = h;
    buf.stride = w * 4;
    buf.data.resize(static_cast<size_t>(buf.stride) * h);
    for (int y = 0; y < h; ++y) {
        for (int x = 0; x < w; ++x) {
            size_t off = static_cast<size_t>(y) * buf.stride + static_cast<size_t>(x) * 4;
            buf.data[off + 0] = b;
            buf.data[off + 1] = g;
            buf.data[off + 2] = r;
            buf.data[off + 3] = 255;
        }
    }
    return buf;
}

static void draw_rect(hss::PixelBuffer& buf, int x, int y, int w, int h,
                      uint8_t b, uint8_t g, uint8_t r, int border = 0,
                      uint8_t bb = 255, uint8_t bg = 255, uint8_t br = 255) {
    for (int yy = std::max(0, y); yy < std::min(buf.height, y + h); ++yy) {
        for (int xx = std::max(0, x); xx < std::min(buf.width, x + w); ++xx) {
            bool is_edge = border > 0 && (xx - x < border || x + w - 1 - xx < border ||
                                          yy - y < border || y + h - 1 - yy < border);
            size_t off = static_cast<size_t>(yy) * buf.stride + static_cast<size_t>(xx) * 4;
            buf.data[off + 0] = is_edge ? bb : b;
            buf.data[off + 1] = is_edge ? bg : g;
            buf.data[off + 2] = is_edge ? br : r;
            buf.data[off + 3] = 255;
        }
    }
}

void test_config_and_pywal() {
    TempDir td;
    fs::path cfg_path = td.path / "config.json";
    fs::create_directories(td.path / "config.d");
    {
        std::ofstream f(cfg_path);
        f << R"({"language":"cs","theme":{"mode":"pywal","pywalPath":")" << (td.path / "wal.json").string() << R"("}})";
    }
    {
        std::ofstream f(td.path / "config.d" / "10-override.json");
        f << R"({"capture":{"pngCompression":7}})";
    }
    {
        std::ofstream f(td.path / "wal.json");
        f << R"({"special":{"background":"#11111b","foreground":"#cdd6f4"},"colors":{"color0":"#11111b","color1":"#f38ba8","color2":"#a6e3a1","color3":"#f9e2af","color4":"#89b4fa","color5":"#cba6f7","color7":"#bac2de","color8":"#585b70","color9":"#eba0ac","color15":"#cdd6f4"}})";
    }
    {
        std::ofstream f(td.path / "api_keys.env");
        f << "GEMINI_API_KEY=\"secret_test_key\"\n";
    }

    auto cfg = hss::ConfigManager::load_config(cfg_path.string());
    CHECK(cfg["language"] == "cs");
    CHECK(cfg["capture"]["pngCompression"] == 7);
    CHECK(hss::ConfigManager::resolve_preset_for_class(cfg, "LibreWolf") == "browser");
    CHECK(hss::ConfigManager::resolve_preset_for_class(cfg, "kitty") == "terminal");
    CHECK(hss::ConfigManager::resolve_preset_for_class(cfg, "steam_app_123") == "game");

    auto pal = hss::ConfigManager::resolve_palette(cfg);
    CHECK(pal.source == "pywal");
    CHECK(!pal.is_light);
    CHECK(pal.accent.to_hex() == "#f38ba8");
    CHECK(pal.selection_border.to_hex() == "#a6e3a1");

    CHECK(hss::ConfigManager::load_env_file_key("GEMINI_API_KEY", cfg_path.string()) == "secret_test_key");
    g_passed++;
}

void test_i18n() {
    CHECK(hss::I18n::sanitize_lang("cs_CZ.UTF-8") == "cs_CZ");
    CHECK(hss::I18n::sanitize_lang("../etc/passwd") == "en");
    hss::I18n i18n;
    i18n.load("cs", "/nonexistent", fs::path(HSS_SOURCE_DIR));
    CHECK(i18n.t("copy") == "Kopírovat");
    CHECK(i18n.t("pin") == "Připnout");
    CHECK(i18n.format_path("saveDesc", "/tmp/a.png").find("/tmp/a.png") != std::string::npos);
    g_passed++;
}

void test_image_ops_and_scaling() {
    auto r = hss::ImageOps::compute_physical_crop(10.0, 20.0, 100.0, 50.0, 1.5, 1920, 1080);
    CHECK(r.x == 15 && r.y == 30 && r.w == 150 && r.h == 75);

    // Clamping guard
    auto rc = hss::ImageOps::compute_physical_crop(1900.0, 1070.0, 100.0, 100.0, 1.0, 1920, 1080);
    CHECK(rc.x >= 0 && rc.y >= 0 && rc.x + rc.w <= 1920 && rc.y + rc.h <= 1080);

    TempDir td;
    auto img = make_solid_bgra(160, 120, 20, 140, 220);
    auto cropped = hss::ImageOps::crop(img, {10, 10, 64, 48});
    CHECK(cropped.width == 64 && cropped.height == 48);

    fs::path png_p = td.path / "roundtrip.png";
    CHECK(hss::ImageOps::save_png(cropped, png_p, 1));
    auto loaded = hss::ImageOps::load_image(png_p);
    CHECK(loaded.has_value());
    CHECK(loaded->width == 64 && loaded->height == 48);
    CHECK(loaded->data[0] == 20 && loaded->data[1] == 140 && loaded->data[2] == 220);

    auto jpg = hss::ImageOps::encode_jpeg_resized(img, 80, 85);
    CHECK(jpg.size() > 100);
    CHECK(!hss::ImageOps::base64_encode(jpg).empty());

    auto dimmed = hss::ImageOps::make_dimmed_copy(img, 0.5);
    CHECK(dimmed.data[2] < img.data[2]);
    g_passed++;
}

void test_hyprland_clients_and_layers_parsing() {
    nlohmann::json clients = nlohmann::json::array({
        {{"at", {0, 0}}, {"size", {1920, 1080}}, {"floating", false}, {"pinned", false},
         {"mapped", true}, {"hidden", false}, {"workspace", {{"id", 1}}}, {"class", "firefox"}, {"title", "Web"}},
    });
    nlohmann::json layers = {
        {"DP-1", {{"levels", {
            {"2", nlohmann::json::array({
                {{"x", 1500}, {"y", 40}, {"w", 380}, {"h", 420}, {"namespace", "caelestia-popout"}},
                {{"x", 0}, {"y", 0}, {"w", 1920}, {"h", 1080}, {"namespace", "fullscreen-backdrop"}},
            })},
        }}}}
    };

    auto parsed = hss::HyprlandIpc::parse_clients_and_layers_json(clients, layers, "DP-1", 1920, 1080);
    CHECK(parsed.size() == 2);
    CHECK(!parsed[0].is_layer && parsed[0].wm_class == "firefox");
    CHECK(parsed[1].is_layer && parsed[1].floating && parsed[1].wm_class == "caelestia-popout");
    g_passed++;
}

void test_cv_workspace_isolation_and_browser_body() {
    auto img = make_solid_bgra(1280, 720, 24, 24, 28);
    // Browser window with dark header bar (y=40..120) and light page viewport (y=120..680)
    draw_rect(img, 60, 40, 1100, 80, 35, 35, 42);
    draw_rect(img, 60, 120, 1100, 560, 238, 238, 242);
    // Inner card inside viewport
    draw_rect(img, 120, 180, 420, 240, 255, 255, 255, 2, 160, 160, 170);

    std::vector<hss::ClientWindow> clients = {
        {60, 40, 1100, 640, false, false, true, false, false, 2, "2", 0, "librewolf", "Browser"},
        // Background workspace window (workspace 9) MUST be filtered out
        {0, 0, 640, 720, false, false, true, false, false, 9, "9", 1, "kitty", "HiddenTerm"},
    };

    TempDir td;
    hss::CvDetectionOptions opts;
    opts.active_workspace_id = 2;
    opts.preset_key = "browser";
    opts.explicit_rating_profile = td.path / "rating.json";

    auto cfg = hss::ConfigManager::default_config();
    auto res = hss::CvDetector::detect(img, clients, cfg, opts);
    CHECK(!res.boxes.empty());

    bool found_browser_win = false;
    bool found_hidden_ws = false;
    bool found_page_body = false;
    for (const auto& b : res.boxes) {
        if (b.wm_class == "librewolf" && b.is_client) found_browser_win = true;
        if (b.wm_class == "kitty") found_hidden_ws = true;
        if (!b.is_client && b.type == "panel" && std::abs(b.y - 120) <= 6 && b.w >= 1000 && b.h >= 500) {
            found_page_body = true;
        }
    }
    CHECK(found_browser_win);
    CHECK(!found_hidden_ws);
    CHECK(found_page_body);
    g_passed++;
}

void test_cv_slot_grid_and_rating_feedback() {
    // 2x4 inventory slot grid
    std::vector<hss::DetectedBox> slots;
    for (int r = 0; r < 2; ++r) {
        for (int c = 0; c < 4; ++c) {
            hss::DetectedBox s;
            s.x = 100 + c * 52;
            s.y = 200 + r * 52;
            s.w = 48;
            s.h = 48;
            s.area = 48 * 48;
            s.type = "slot";
            slots.push_back(s);
        }
    }
    auto synth = hss::CvDetector::cluster_slots_and_grids(slots);
    int rows = 0, grids = 0;
    for (const auto& b : synth) {
        if (b.type == "grid_row") rows++;
        if (b.type == "grid_container") grids++;
    }
    CHECK(rows == 2);
    CHECK(grids == 1);

    TempDir td;
    auto cfg = hss::ConfigManager::default_config();
    fs::path prof_p = td.path / "rating.json";
    auto p1 = hss::RatingEngine::record_feedback("slot", 48, 48, true, "game", cfg, prof_p);
    CHECK(p1.samples == 1);
    auto p2 = hss::RatingEngine::record_feedback("slot", 48, 48, true, "game", cfg, prof_p);
    CHECK(p2.samples == 2);
    CHECK(p2.biases.at("game:slot:sm") > 0.0);
    g_passed++;
}

void test_ai_box_extraction_and_snapping() {
    std::string raw = "<think>reasoning</think>\n```json\n"
                      R"([{"label":"Sidebar","type":"sidebar","x1":10,"y1":50,"x2":210,"y2":950,"confidence":0.91},)"
                      R"({"label":"Input","type":"search","bbox_2d":[100,300,150,700],"confidence":0.85}])"
                      "\n```";
    auto boxes = hss::AiClient::extract_ai_boxes(raw, 1000, 1000);
    CHECK(boxes.size() == 2);
    CHECK(boxes[0].type == "panel" && boxes[0].x == 10 && boxes[0].w == 200);
    CHECK(boxes[1].type == "input" && boxes[1].x == 300 && boxes[1].y == 100);

    hss::DetectedBox cv_ref;
    cv_ref.x = 12; cv_ref.y = 48; cv_ref.w = 198; cv_ref.h = 902;
    hss::AiClient::snap_to_cv(boxes, {cv_ref}, 24);
    CHECK(boxes[0].x == 12 && boxes[0].w == 198);
    g_passed++;
}

void test_selector_floating_occlusion_guard() {
    hss::SmartSelector sel;
    auto cfg = hss::ConfigManager::default_config();
    sel.init(1920, 1080, 1.0, "universal", "default", cfg);

    hss::DetectedBox bg_panel;
    bg_panel.x = 100; bg_panel.y = 100; bg_panel.w = 1200; bg_panel.h = 800; bg_panel.area = 1200 * 800;
    bg_panel.type = "panel";

    hss::DetectedBox layer_pop;
    layer_pop.x = 400; layer_pop.y = 200; layer_pop.w = 320; layer_pop.h = 300; layer_pop.area = 320 * 300;
    layer_pop.type = "floating_window"; layer_pop.is_client = true; layer_pop.floating = true; layer_pop.is_layer = true;

    sel.set_cv_boxes({bg_panel, layer_pop});
    sel.on_pointer_move(500, 300);

    // Background panel extending outside floating popout MUST NOT leak into candidate hierarchy
    for (const auto& c : sel.hierarchy()) {
        if (c.source == "screen") continue;
        CHECK(c.x >= 394 && c.x + c.w <= 726);
    }
    g_passed++;
}

void test_cli_binary_contract() {
    std::string bin = HSS_BINARY_PATH;
    {
        auto [rc, out] = run_cmd_capture({bin, "--help"});
        CHECK(rc == 0);
        CHECK(out.find("Usage:") != std::string::npos);
        CHECK(out.find("daemon") != std::string::npos);
    }
    {
        auto [rc, out] = run_cmd_capture({bin, "--version"});
        CHECK(rc == 0);
        CHECK(out.find("hyprsmartshot v") != std::string::npos);
    }
    {
        auto [rc, out] = run_cmd_capture({bin, "--unknown-flag"});
        CHECK(rc == 1);
        CHECK(out.find("Error: Unknown option") != std::string::npos);
    }
    {
        auto [rc, out] = run_cmd_capture({bin, "invalid_cmd"});
        CHECK(rc == 1);
        CHECK(out.find("Error: Unknown command") != std::string::npos);
    }
    {
        auto [rc, out] = run_cmd_capture({bin, "pin"});
        CHECK(rc == 1);
        CHECK(out.find("Error: Missing image path") != std::string::npos);
    }
    {
        auto [rc, out] = run_cmd_capture({bin, "pin", "/tmp/does_not_exist_99999.png"});
        CHECK(rc == 1);
        CHECK(out.find("Error: Image not found") != std::string::npos);
    }
    {
        auto [rc, out] = run_cmd_capture({bin, "--doctor"});
        CHECK(rc == 0);
        CHECK(out.find("HyprSmartShot Doctor") != std::string::npos);
    }
    CHECK(hss::PinWindow::is_temporary_path("/tmp/hyprsmartshot_pin_123.png"));
    CHECK(!hss::PinWindow::is_temporary_path("/home/user/Pictures/shot.png"));
    g_passed++;
}

int main() {
    test_config_and_pywal();
    test_i18n();
    test_image_ops_and_scaling();
    test_hyprland_clients_and_layers_parsing();
    test_cv_workspace_isolation_and_browser_body();
    test_cv_slot_grid_and_rating_feedback();
    test_ai_box_extraction_and_snapping();
    test_selector_floating_occlusion_guard();
    test_cli_binary_contract();
    std::cout << "ALL " << g_passed << " C++ TEST SUITES PASSED\n";
    return 0;
}
