"""Lightweight, dependency-free User-Agent parsing for the events.envelope DeviceInfo
fields. Good enough for this project's purposes — not worth adding a PyPI dependency for."""

from __future__ import annotations

from events.envelope import DeviceInfo


def parse_device_info(user_agent: str | None) -> DeviceInfo:
    if not user_agent:
        return DeviceInfo()

    ua = user_agent.lower()

    if "ipad" in ua or "tablet" in ua:
        device_type = "tablet"
    elif "mobile" in ua or "iphone" in ua or "android" in ua:
        device_type = "mobile"
    else:
        device_type = "desktop"

    if "windows" in ua:
        operating_system = "Windows"
    elif "mac os" in ua or "macintosh" in ua:
        operating_system = "macOS"
    elif "android" in ua:
        operating_system = "Android"
    elif "iphone" in ua or "ipad" in ua or "ios" in ua:
        operating_system = "iOS"
    elif "linux" in ua:
        operating_system = "Linux"
    else:
        operating_system = None

    if "edg/" in ua:
        browser = "Edge"
    elif "chrome" in ua and "edg/" not in ua:
        browser = "Chrome"
    elif "firefox" in ua:
        browser = "Firefox"
    elif "safari" in ua and "chrome" not in ua:
        browser = "Safari"
    else:
        browser = None

    return DeviceInfo(device_type=device_type, operating_system=operating_system, browser=browser)
