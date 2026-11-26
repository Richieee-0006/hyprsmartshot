#include "wayland/clipboard.hpp"

#include <cstring>
#include <fcntl.h>
#include <malloc.h>
#include <signal.h>
#include <sys/wait.h>
#include <unistd.h>

#if HSS_HAVE_EXT_DATA_CONTROL
#include "ext-data-control-v1-client-protocol.h"
#endif

namespace hss {

Clipboard::~Clipboard() {
    detach();
}

void Clipboard::clear_buffer() {
    std::vector<uint8_t>().swap(payload_);
    mime_type_.clear();
    malloc_trim(0);
}

void Clipboard::detach() {
#if HSS_HAVE_EXT_DATA_CONTROL
    if (source_) {
        ext_data_control_source_v1_destroy(source_);
        source_ = nullptr;
    }
    if (device_) {
        ext_data_control_device_v1_destroy(device_);
        device_ = nullptr;
    }
    mgr_ = nullptr;
    display_ = nullptr;
#endif
    clear_buffer();
}

#if HSS_HAVE_EXT_DATA_CONTROL
void Clipboard::attach_ext(wl_display* display, ext_data_control_manager_v1* mgr, wl_seat* seat) {
    detach();
    if (!display || !mgr || !seat) return;
    display_ = display;
    mgr_ = mgr;
    device_ = ext_data_control_manager_v1_get_data_device(mgr_, seat);
    static const ext_data_control_device_v1_listener dev_listener = {
        .data_offer = [](void*, ext_data_control_device_v1*, ext_data_control_offer_v1* offer) {
            if (offer) ext_data_control_offer_v1_destroy(offer);
        },
        .selection = [](void*, ext_data_control_device_v1*, ext_data_control_offer_v1* offer) {
            if (offer) ext_data_control_offer_v1_destroy(offer);
        },
        .finished = [](void* data, ext_data_control_device_v1*) {
            static_cast<Clipboard*>(data)->detach();
        },
        .primary_selection = [](void*, ext_data_control_device_v1*, ext_data_control_offer_v1* offer) {
            if (offer) ext_data_control_offer_v1_destroy(offer);
        },
    };
    if (device_) {
        ext_data_control_device_v1_add_listener(device_, &dev_listener, this);
    }
}

bool Clipboard::set_native(std::vector<uint8_t> data, const std::string& mime_type) {
    if (!mgr_ || !device_ || !display_) return false;

    if (source_) {
        ext_data_control_source_v1_destroy(source_);
        source_ = nullptr;
    }

    payload_ = std::move(data);
    mime_type_ = mime_type;

    source_ = ext_data_control_manager_v1_create_data_source(mgr_);
    if (!source_) return false;

    ext_data_control_source_v1_offer(source_, mime_type_.c_str());
    if (mime_type_ == "text/plain;charset=utf-8") {
        ext_data_control_source_v1_offer(source_, "text/plain");
        ext_data_control_source_v1_offer(source_, "UTF8_STRING");
    }

    static const ext_data_control_source_v1_listener src_listener = {
        .send = [](void* data, ext_data_control_source_v1*, const char*, int32_t fd) {
            auto* self = static_cast<Clipboard*>(data);
            // Fork tiny writer for large images so daemon event loop never blocks on slow paste client
            if (self->payload_.size() > 65536) {
                pid_t pid = ::fork();
                if (pid == 0) {
                    size_t written = 0;
                    while (written < self->payload_.size()) {
                        ssize_t n = ::write(fd, self->payload_.data() + written,
                                            self->payload_.size() - written);
                        if (n <= 0) break;
                        written += static_cast<size_t>(n);
                    }
                    ::close(fd);
                    ::_exit(0);
                }
                ::close(fd);
                return;
            }
            size_t written = 0;
            while (written < self->payload_.size()) {
                ssize_t n = ::write(fd, self->payload_.data() + written,
                                    self->payload_.size() - written);
                if (n <= 0) break;
                written += static_cast<size_t>(n);
            }
            ::close(fd);
        },
        .cancelled = [](void* data, ext_data_control_source_v1* src) {
            auto* self = static_cast<Clipboard*>(data);
            if (self->source_ == src) {
                ext_data_control_source_v1_destroy(self->source_);
                self->source_ = nullptr;
                self->clear_buffer();
            } else {
                ext_data_control_source_v1_destroy(src);
            }
        },
    };
    ext_data_control_source_v1_add_listener(source_, &src_listener, this);
    ext_data_control_device_v1_set_selection(device_, source_);
    wl_display_flush(display_);
    return true;
}
#endif

bool Clipboard::copy_via_wl_copy(const std::vector<uint8_t>& data, const std::string& mime_type) {
    int pipefd[2];
    if (::pipe2(pipefd, O_CLOEXEC) < 0) return false;

    pid_t pid = ::fork();
    if (pid < 0) {
        ::close(pipefd[0]);
        ::close(pipefd[1]);
        return false;
    }

    if (pid == 0) {
        ::dup2(pipefd[0], STDIN_FILENO);
        ::close(pipefd[0]);
        ::close(pipefd[1]);
        int devnull = ::open("/dev/null", O_WRONLY);
        if (devnull >= 0) {
            ::dup2(devnull, STDOUT_FILENO);
            ::dup2(devnull, STDERR_FILENO);
            ::close(devnull);
        }
        const char* argv[] = {"wl-copy", "--type", mime_type.c_str(), nullptr};
        ::execvp("wl-copy", const_cast<char* const*>(argv));
        ::_exit(127);
    }

    ::close(pipefd[0]);
    size_t written = 0;
    while (written < data.size()) {
        ssize_t n = ::write(pipefd[1], data.data() + written, data.size() - written);
        if (n <= 0) break;
        written += static_cast<size_t>(n);
    }
    ::close(pipefd[1]);

    int status = 0;
    ::waitpid(pid, &status, 0);
    return WIFEXITED(status) && WEXITSTATUS(status) == 0;
}

bool Clipboard::copy_text_via_wl_copy(const std::string& text) {
    std::vector<uint8_t> bytes(text.begin(), text.end());
    return copy_via_wl_copy(bytes, "text/plain;charset=utf-8");
}

}  // namespace hss
