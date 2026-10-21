"""Fixed-window rate limiting: at most N requests per key in each window of W seconds."""
import ipaddress
import math
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0  # meaningful only when the request is denied


def current_window(now: float, window_seconds: int) -> Tuple[int, int]:
    """Return the start of the window containing `now` and the whole seconds until it ends (at least 1)."""
    start = int(now // window_seconds) * window_seconds
    return start, max(1, math.ceil(start + window_seconds - now))


IPV6_CLIENT_PREFIX = 64  # ISPs hand each customer at least a /64, so it identifies one client


def client_key(ip: str) -> str:
    """Rate limit key for a client IP: the address for IPv4, its /64 network for IPv6.

    One IPv6 client controls every address in its /64, so keying by the full address
    would let it rotate addresses and get a fresh budget each time.
    """
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return ip  # not an IP (e.g. a test client name): use it as is
    if address.version == 6 and address.ipv4_mapped:
        return str(address.ipv4_mapped)
    if address.version == 6:
        return str(ipaddress.ip_network((address, IPV6_CLIENT_PREFIX), strict=False))
    return str(address)


def decide(count: int, limit: int, retry_after_seconds: int) -> RateLimitDecision:
    """`count` includes the current request."""
    if count <= limit:
        return RateLimitDecision(allowed=True)
    return RateLimitDecision(allowed=False, retry_after_seconds=retry_after_seconds)
