#pragma once

#include <cstddef>
#include <cstdint>
#include <wayland-client.h>

namespace hss {

class ShmBuffer {
public:
    ShmBuffer() = default;
    ~ShmBuffer();

    ShmBuffer(const ShmBuffer&) = delete;
    ShmBuffer& operator=(const ShmBuffer&) = delete;
    ShmBuffer(ShmBuffer&& other) noexcept;
    ShmBuffer& operator=(ShmBuffer&& other) noexcept;

    bool allocate(wl_shm* shm, int width, int height, uint32_t format = WL_SHM_FORMAT_ARGB8888, int stride = 0);
    void release();

    wl_buffer* buffer() const { return buffer_; }
    uint8_t* data() const { return data_; }
    int width() const { return width_; }
    int height() const { return height_; }
    int stride() const { return stride_; }
    size_t size() const { return size_; }
    bool valid() const { return buffer_ != nullptr && data_ != nullptr; }

private:
    wl_buffer* buffer_ = nullptr;
    uint8_t* data_ = nullptr;
    size_t size_ = 0;
    int fd_ = -1;
    int width_ = 0;
    int height_ = 0;
    int stride_ = 0;
};

}  // namespace hss
