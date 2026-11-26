#pragma once

#include <cstdint>
#include <string>
#include <vector>
#include <wayland-client.h>

#if HSS_HAVE_EXT_DATA_CONTROL
struct ext_data_control_manager_v1;
struct ext_data_control_device_v1;
struct ext_data_control_source_v1;
#endif

namespace hss {

class Clipboard {
public:
    Clipboard() = default;
    ~Clipboard();

    Clipboard(const Clipboard&) = delete;
    Clipboard& operator=(const Clipboard&) = delete;

#if HSS_HAVE_EXT_DATA_CONTROL
    void attach_ext(wl_display* display, ext_data_control_manager_v1* mgr, wl_seat* seat);
    bool set_native(std::vector<uint8_t> data, const std::string& mime_type);
#endif
    void detach();
    void clear_buffer();

    // Direct pipe to wl-copy (zero shell, zero temp files; persists after process exit)
    static bool copy_via_wl_copy(const std::vector<uint8_t>& data, const std::string& mime_type);
    static bool copy_text_via_wl_copy(const std::string& text);

private:
#if HSS_HAVE_EXT_DATA_CONTROL
    wl_display* display_ = nullptr;
    ext_data_control_manager_v1* mgr_ = nullptr;
    ext_data_control_device_v1* device_ = nullptr;
    ext_data_control_source_v1* source_ = nullptr;
#endif
    std::string mime_type_;
    std::vector<uint8_t> payload_;
};

}  // namespace hss
