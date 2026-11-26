#include "wayland/shm.hpp"

#include <cstring>
#include <sys/mman.h>
#include <unistd.h>

namespace hss {

ShmBuffer::~ShmBuffer() {
    release();
}

ShmBuffer::ShmBuffer(ShmBuffer&& other) noexcept
    : buffer_(other.buffer_),
      data_(other.data_),
      size_(other.size_),
      fd_(other.fd_),
      width_(other.width_),
      height_(other.height_),
      stride_(other.stride_) {
    other.buffer_ = nullptr;
    other.data_ = nullptr;
    other.size_ = 0;
    other.fd_ = -1;
    other.width_ = 0;
    other.height_ = 0;
    other.stride_ = 0;
}

ShmBuffer& ShmBuffer::operator=(ShmBuffer&& other) noexcept {
    if (this != &other) {
        release();
        buffer_ = other.buffer_;
        data_ = other.data_;
        size_ = other.size_;
        fd_ = other.fd_;
        width_ = other.width_;
        height_ = other.height_;
        stride_ = other.stride_;
        other.buffer_ = nullptr;
        other.data_ = nullptr;
        other.size_ = 0;
        other.fd_ = -1;
        other.width_ = 0;
        other.height_ = 0;
        other.stride_ = 0;
    }
    return *this;
}

bool ShmBuffer::allocate(wl_shm* shm, int width, int height, uint32_t format, int stride) {
    release();
    if (!shm || width <= 0 || height <= 0) return false;

    int row_stride = (stride > 0) ? stride : (width * 4);
    size_t total = static_cast<size_t>(row_stride) * static_cast<size_t>(height);

    int fd = ::memfd_create("hyprsmartshot-shm", MFD_CLOEXEC);
    if (fd < 0) return false;
    if (::ftruncate(fd, static_cast<off_t>(total)) < 0) {
        ::close(fd);
        return false;
    }

    void* ptr = ::mmap(nullptr, total, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (ptr == MAP_FAILED) {
        ::close(fd);
        return false;
    }

    wl_shm_pool* pool = wl_shm_create_pool(shm, fd, static_cast<int32_t>(total));
    if (!pool) {
        ::munmap(ptr, total);
        ::close(fd);
        return false;
    }

    wl_buffer* buf = wl_shm_pool_create_buffer(pool, 0, width, height, row_stride, format);
    wl_shm_pool_destroy(pool);
    if (!buf) {
        ::munmap(ptr, total);
        ::close(fd);
        return false;
    }

    buffer_ = buf;
    data_ = static_cast<uint8_t*>(ptr);
    size_ = total;
    fd_ = fd;
    width_ = width;
    height_ = height;
    stride_ = row_stride;
    return true;
}

void ShmBuffer::release() {
    if (buffer_) {
        wl_buffer_destroy(buffer_);
        buffer_ = nullptr;
    }
    if (data_) {
        ::munmap(data_, size_);
        data_ = nullptr;
    }
    if (fd_ >= 0) {
        ::close(fd_);
        fd_ = -1;
    }
    size_ = 0;
    width_ = 0;
    height_ = 0;
    stride_ = 0;
}

}  // namespace hss
