from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

import re

__all__ = ("hide_ip",)

def hide_ip(text: str, hide_it: bool) -> str | Any:
    ipv4_re = r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    ipv6_re = r"([a-f0-9:]+:+)+[a-f0-9]+"

    if hide_it and isinstance(text, str):
        text = re.sub(ipv4_re, "{the-cat-snatched-your-ip-address}", text)
        text = re.sub(ipv6_re, "{the-cat-snatched-your-ip-address}", text)

    return text
