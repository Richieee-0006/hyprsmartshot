#include "core/actions.hpp"
#include "vision/vision_bridge.hpp"

#include <chrono>
#include <cstdlib>
#include <ctime>
#include <fcntl.h>
#include <filesystem>
#include <iomanip>
#include <sstream>
#include <sys/wait.h>
#include <unistd.h>

namespace hss {

namespace fs = std::filesystem;

namespace {

std::string shell_escape_single(const std::string& s) {
    std::string out = "'";
    for (char c : s) {
        if (c == '\'') out += "'\\''";
        else out.push_back(c);
    }
    out.push_back('\'');
    return out;
}

std::string make_temp_png_path(const std::string& tag) {
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                  std::chrono::steady_clock::now().time_since_epoch())
                  .count();
    return "/tmp/hyprsmartshot_" + tag + "_" + std::to_string(getpid()) + "_" + std::to_string(ms) + ".png";
}

std::string run_capture_stdout(const std::vector<std::string>& argv) {
    int pipefd[2];
    if (::pipe2(pipefd, O_CLOEXEC) < 0) return "";

    pid_t pid = ::fork();
    if (pid < 0) {
        ::close(pipefd[0]);
        ::close(pipefd[1]);
        return "";
    }
    if (pid == 0) {
        ::dup2(pipefd[1], STDOUT_FILENO);
        int devnull = ::open("/dev/null", O_WRONLY);
        if (devnull >= 0) {
            ::dup2(devnull, STDERR_FILENO);
            ::close(devnull);
        }
        ::close(pipefd[0]);
        ::close(pipefd[1]);
        std::vector<char*> cargv;
        cargv.reserve(argv.size() + 1);
        for (const auto& a : argv) cargv.push_back(const_cast<char*>(a.c_str()));
        cargv.push_back(nullptr);
        ::execvp(cargv[0], cargv.data());
        ::_exit(127);
    }

    ::close(pipefd[1]);
    std::string out;
    char buf[4096];
    ssize_t n;
    while ((n = ::read(pipefd[0], buf, sizeof(buf))) > 0) {
        out.append(buf, static_cast<size_t>(n));
    }
    ::close(pipefd[0]);
    int st = 0;
    ::waitpid(pid, &st, 0);
    return out;
}

std::string resolve_self_exe(const std::string& hint) {
    if (!hint.empty()) return hint;
    std::error_code ec;
    auto p = fs::read_symlink("/proc/self/exe", ec);
    return ec ? std::string("hyprsmartshot") : p.string();
}

}  // namespace

bool Actions::command_exists(const std::string& cmd) {
    if (cmd.empty()) return false;
    if (cmd.find('/') != std::string::npos) {
        return ::access(cmd.c_str(), X_OK) == 0;
    }
    const char* path_env = std::getenv("PATH");
    if (!path_env) return false;
    std::stringstream ss(path_env);
    std::string dir;
    while (std::getline(ss, dir, ':')) {
        if (dir.empty()) dir = ".";
        std::string full = dir + "/" + cmd;
        if (::access(full.c_str(), X_OK) == 0) return true;
    }
    return false;
}

void Actions::spawn_detached(const std::vector<std::string>& argv) {
    if (argv.empty()) return;
    pid_t pid = ::fork();
    if (pid < 0) return;
    if (pid == 0) {
        ::setsid();
        pid_t grand = ::fork();
        if (grand != 0) ::_exit(0);
        int devnull = ::open("/dev/null", O_RDWR);
        if (devnull >= 0) {
            ::dup2(devnull, STDIN_FILENO);
            ::dup2(devnull, STDOUT_FILENO);
            ::dup2(devnull, STDERR_FILENO);
            ::close(devnull);
        }
        std::vector<char*> cargv;
        cargv.reserve(argv.size() + 1);
        for (const auto& a : argv) cargv.push_back(const_cast<char*>(a.c_str()));
        cargv.push_back(nullptr);
        ::execvp(cargv[0], cargv.data());
        ::_exit(127);
    }
    int st = 0;
    ::waitpid(pid, &st, 0);
}

void Actions::play_shutter() {
    if (command_exists("canberra-gtk-play")) {
        spawn_detached({"canberra-gtk-play", "-i", "camera-shutter"});
    } else if (command_exists("paplay")) {
        spawn_detached({"paplay", "/usr/share/sounds/freedesktop/stereo/camera-shutter.oga"});
    }
}

void Actions::notify(const std::string& title,
                     const std::string& body,
                     const std::string& toast_type,
                     const std::string& icon,
                     const std::string& image_path) {
    if (command_exists("caelestia-toast")) {
        spawn_detached({"caelestia-toast", "-t", toast_type, "-i", icon, "-a", "HyprSmartShot", title, body});
        return;
    }
    if (command_exists("notify-send")) {
        std::vector<std::string> args = {"notify-send", "-a", "HyprSmartShot"};
        if (!image_path.empty()) {
            args.push_back("-i");
            args.push_back(image_path);
            args.push_back("-h");
            args.push_back("string:image-path:" + image_path);
        }
        args.push_back(title);
        args.push_back(body);
        spawn_detached(args);
    }
}

void Actions::run_hook(const std::string& hook_template, const std::string& file_path) {
    if (hook_template.empty()) return;
    std::string cmd = hook_template;
    std::string esc = shell_escape_single(file_path);
    const std::string needle = "{path}";
    size_t pos = 0;
    while ((pos = cmd.find(needle, pos)) != std::string::npos) {
        cmd.replace(pos, needle.size(), esc);
        pos += esc.size();
    }
    spawn_detached({"sh", "-c", cmd});
}

std::string Actions::timestamp_now() {
    std::time_t t = std::time(nullptr);
    std::tm tm_buf{};
    localtime_r(&t, &tm_buf);
    std::ostringstream oss;
    oss << std::put_time(&tm_buf, "%Y-%m-%d_%H-%M-%S");
    return oss.str();
}

void Actions::copy_crop(const PixelBuffer& cropped,
                        const nlohmann::json& cfg,
                        const I18n& i18n,
                        Clipboard* daemon_clipboard) {
    auto png = ImageOps::encode_png(cropped, 0);
    if (png.empty()) return;

    play_shutter();

    bool copied = false;
#if HSS_HAVE_EXT_DATA_CONTROL
    if (daemon_clipboard) {
        copied = daemon_clipboard->set_native(png, "image/png");
    }
#endif
    if (!copied) {
        Clipboard::copy_via_wl_copy(png, "image/png");
    }

    std::string hook = cfg.value("postCopyHook", std::string());
    if (!hook.empty()) {
        std::string tmp = make_temp_png_path("copy");
        ImageOps::save_png(cropped, tmp, 0);
        run_hook(hook + "; (sleep 10 && rm -f " + shell_escape_single(tmp) + ") &", tmp);
    }

    notify(i18n.t("copyTitle", "Screenshot Copied"),
           i18n.t("copyDesc", "Region copied to clipboard"),
           "success", "content_copy");
}

fs::path Actions::save_crop(const PixelBuffer& cropped,
                            const nlohmann::json& cfg,
                            const I18n& i18n,
                            bool is_fullscreen,
                            Clipboard* daemon_clipboard) {
    fs::path save_dir = ConfigManager::resolve_save_dir(cfg);
    fs::path output_path = save_dir / ("screenshot-" + timestamp_now() + ".png");

    int comp = 4;
    bool copy_after = true;
    if (cfg.contains("capture") && cfg["capture"].is_object()) {
        comp = cfg["capture"].value("pngCompression", 4);
        copy_after = cfg["capture"].value("copyAfterSave", true);
    }

    auto png = ImageOps::encode_png(cropped, comp);
    if (png.empty()) return {};

    std::error_code ec;
    fs::create_directories(save_dir, ec);
    {
        FILE* f = std::fopen(output_path.c_str(), "wb");
        if (!f) return {};
        std::fwrite(png.data(), 1, png.size(), f);
        std::fclose(f);
    }

    play_shutter();

    if (copy_after) {
        bool copied = false;
#if HSS_HAVE_EXT_DATA_CONTROL
        if (daemon_clipboard) copied = daemon_clipboard->set_native(png, "image/png");
#endif
        if (!copied) Clipboard::copy_via_wl_copy(png, "image/png");
    }

    std::string title = is_fullscreen ? i18n.t("fullscreenTitle", "Fullscreen Captured")
                                      : i18n.t("saveTitle", "Screenshot Saved");
    std::string desc = is_fullscreen
                           ? i18n.format_path("fullscreenDesc", output_path.string(),
                                              "Saved to {path} and copied to clipboard")
                           : i18n.format_path("saveDesc", output_path.string(),
                                              "Saved to {path} and copied to clipboard");
    notify(title, desc, "success", "save", output_path.string());

    std::string hook = cfg.value("postSaveHook", std::string());
    if (!hook.empty()) run_hook(hook, output_path.string());
    return output_path;
}

void Actions::pin_crop(const PixelBuffer& cropped,
                       int logical_x, int logical_y, int logical_w, int logical_h,
                       const ThemePalette& palette,
                       const I18n& i18n,
                       const std::string& self_exe) {
    std::string tmp = make_temp_png_path("pin");
    if (!ImageOps::save_png(cropped, tmp, 0)) return;

    play_shutter();
    notify(i18n.t("pinTitle", "Pinned to Screen"),
           i18n.t("pinDesc", "Region pinned as floating window"),
           "info", "push_pin", tmp);

    std::string exe = resolve_self_exe(self_exe);
    spawn_detached({
        exe, "pin",
        "--border-color", palette.pin_border.to_hex(),
        "--bg-color", palette.card_background.to_hex(),
        "--border-width", std::to_string(std::max(1, static_cast<int>(std::lround(palette.pin_border_width)))),
        tmp,
        std::to_string(logical_x),
        std::to_string(logical_y),
        std::to_string(logical_w),
        std::to_string(logical_h),
    });
}

void Actions::annotate_crop(const PixelBuffer& cropped,
                            const nlohmann::json& cfg,
                            const I18n& i18n) {
    fs::path save_dir = ConfigManager::resolve_save_dir(cfg);
    std::error_code ec;
    fs::create_directories(save_dir, ec);
    fs::path output_path = save_dir / ("annotation-" + timestamp_now() + ".png");
    std::string tmp = make_temp_png_path("annot");
    if (!ImageOps::save_png(cropped, tmp, 0)) return;

    play_shutter();

    if (command_exists("satty")) {
        std::string copy_desc = i18n.t("copyDesc", "Region copied to clipboard");
        std::string satty_copy =
            "sh -c 'wl-copy --type image/png && (caelestia-toast -t success -i content_copy -a Satty \"$1\" \"$2\" 2>/dev/null || notify-send -a Satty \"$1\" \"$2\" 2>/dev/null || true)' _ 'Satty' " +
            shell_escape_single(copy_desc);
        std::string cmd = "satty --filename " + shell_escape_single(tmp) +
                          " --output-filename " + shell_escape_single(output_path.string()) +
                          " --early-exit --copy-command " + shell_escape_single(satty_copy) +
                          " --initial-tool brush; rm -f " + shell_escape_single(tmp);
        spawn_detached({"sh", "-c", cmd});
    } else if (command_exists("swappy")) {
        std::string cmd = "swappy -f " + shell_escape_single(tmp) +
                          " -o " + shell_escape_single(output_path.string()) +
                          "; rm -f " + shell_escape_single(tmp);
        spawn_detached({"sh", "-c", cmd});
    } else {
        auto png = ImageOps::encode_png(cropped, 0);
        Clipboard::copy_via_wl_copy(png, "image/png");
        notify(i18n.t("annotateNotFoundTitle", "Annotation Editor Not Found"),
               i18n.t("annotateNotFoundDesc", "Region copied to clipboard."),
               "warn", "error", tmp);
        spawn_detached({"sh", "-c", "sleep 10 && rm -f " + shell_escape_single(tmp)});
    }
}

void Actions::ocr_crop(const PixelBuffer& cropped,
                       const std::string& ocr_langs,
                       const nlohmann::json& cfg,
                       const I18n& i18n,
                       Clipboard* daemon_clipboard) {
    play_shutter();

    if (!command_exists("tesseract")) {
        auto png = ImageOps::encode_png(cropped, 0);
        bool copied = false;
#if HSS_HAVE_EXT_DATA_CONTROL
        if (daemon_clipboard) copied = daemon_clipboard->set_native(png, "image/png");
#endif
        if (!copied) Clipboard::copy_via_wl_copy(png, "image/png");
        notify(i18n.t("ocrNotFoundTitle", "OCR Engine Not Found"),
               i18n.t("ocrNotFoundDesc", "Tesseract not installed. Copied image instead."),
               "warn", "error");
        return;
    }

    std::string tmp = make_temp_png_path("ocr");
    if (!ImageOps::save_png(cropped, tmp, 0)) return;
    std::string langs = ocr_langs.empty() ? cfg.value("ocrLanguages", std::string("eng")) : ocr_langs;
    if (langs.empty()) langs = "eng";

    std::string title_ok = i18n.t("ocrTitle", "OCR Completed");
    std::string desc_ok = i18n.t("ocrDesc", "Recognized text copied to clipboard");
    std::string title_empty = i18n.t("ocrNoTextTitle", "OCR Result");
    std::string desc_empty = i18n.t("ocrNoTextDesc", "No text recognized in selection");

    pid_t pid = ::fork();
    if (pid == 0) {
        ::setsid();
        pid_t grand = ::fork();
        if (grand != 0) ::_exit(0);
        std::string text = run_capture_stdout({"tesseract", tmp, "stdout", "-l", langs});
        std::error_code ec;
        fs::remove(tmp, ec);

        bool has_non_ws = false;
        for (unsigned char c : text) {
            if (!std::isspace(c)) { has_non_ws = true; break; }
        }
        if (has_non_ws) {
            Clipboard::copy_text_via_wl_copy(text);
            notify(title_ok, desc_ok, "success", "text_fields");
        } else {
            notify(title_empty, desc_empty, "warn", "text_format");
        }
        ::_exit(0);
    }
    if (pid > 0) {
        int st = 0;
        ::waitpid(pid, &st, 0);
    }
}

void Actions::ai_vision_crop(const PixelBuffer& cropped,
                             const std::string& action_mode,
                             const nlohmann::json& cfg,
                             const I18n& i18n,
                             Clipboard*) {
    play_shutter();
    PixelBuffer copy_buf = cropped;
    nlohmann::json cfg_copy = cfg;
    std::string ok_title = i18n.t("aiDoneTitle", "AI Vision Complete");
    std::string fail_title = i18n.t("aiFailTitle", "AI Vision Failed");
    std::string fail_desc = i18n.t("aiFailDesc", "Failed to reach configured AI provider.");

    pid_t pid = ::fork();
    if (pid == 0) {
        ::setsid();
        pid_t grand = ::fork();
        if (grand != 0) ::_exit(0);
        auto res = VisionBridge::run_ai_action_forked(copy_buf, action_mode, cfg_copy);
        if (res.ok && !res.text.empty()) {
            Clipboard::copy_text_via_wl_copy(res.text);
            std::string preview = res.text;
            for (char& c : preview) if (c == '\n' || c == '\r') c = ' ';
            if (preview.size() > 120) preview.resize(120);
            notify(ok_title, preview, "success", "auto_awesome");
        } else {
            notify(fail_title, res.error.empty() ? fail_desc : res.error, "error", "error");
        }
        ::_exit(0);
    }
    if (pid > 0) {
        int st = 0;
        ::waitpid(pid, &st, 0);
    }
}

void Actions::launch_settings_gui(const std::string& self_exe, const std::string& tab) {
    std::string exe = resolve_self_exe(self_exe);
    fs::path sibling = fs::path(exe).parent_path() / "hyprsmartshot-settings";
    std::string bin = fs::exists(sibling) ? sibling.string() : std::string("hyprsmartshot-settings");
    if (!command_exists(bin)) return;
    std::vector<std::string> args = {bin};
    if (!tab.empty()) {
        args.push_back("--tab");
        args.push_back(tab);
    }
    spawn_detached(args);
}

}  // namespace hss
