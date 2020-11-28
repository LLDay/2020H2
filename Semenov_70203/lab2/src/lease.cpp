#include "dhcp/lease.h"

#include <limits.h>
#include "dhcp/ip_allocator.h"
#include "dhcp/net_int.h"

namespace dhcp {

Lease::Lease() noexcept : mAllocator{nullptr}, mIsActive{false} {}

Lease::Lease(IpType ip, net32 time, IpAllocator * allocator) noexcept
    : mIp{ip}, mAllocator{allocator}, mIsActive{true} {
    std::unique_lock lock{mMutex};
    mTimer.setCallback([this]() { this->release(); });
    if (time != INFINITY_TIME)
        mTimer.start(time);
}

Lease::Lease(Lease && other) noexcept {
    assign(std::move(other));
}

Lease::~Lease() noexcept {
    release();
}

bool Lease::isActive() const noexcept {
    std::unique_lock lock{mMutex};
    return mIsActive;
}

IpType Lease::ip() const noexcept {
    std::unique_lock lock{mMutex};
    return mIp;
}

net32 Lease::remainingTime() const noexcept {
    return mTimer.remainingTime();
}

void Lease::updateTime(net32 time) noexcept {
    mTimer.start(time);
}

void Lease::release() noexcept {
    std::lock_guard lock{mMutex};
    if (mIsActive) {
        mAllocator->deallocate(mIp);
        mIsActive.store(false);
        mTimer.stop();
    }
}

Lease & Lease::operator=(Lease && other) noexcept {
    assign(std::move(other));
    return *this;
}

void Lease::assign(Lease && other) noexcept {
    std::unique_lock l1{other.mMutex, std::defer_lock};
    std::unique_lock l2{mMutex, std::defer_lock};
    std::lock(l1, l2);

    mIp = other.mIp;
    mTimer = std::move(other.mTimer);
    mTimer.setCallback([this]() { this->release(); });
    mAllocator = other.mAllocator;
    other.mAllocator = nullptr;
    mIsActive = other.mIsActive.exchange(false);
}

}  // namespace dhcp