"""Discover LAN URLs without external services or internet connections."""

from __future__ import annotations

import ipaddress
import socket


def _lan_address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    if (
        address.is_loopback or address.is_unspecified or address.is_multicast
        or address.is_link_local
        or address == ipaddress.IPv4Address("255.255.255.255")
        or (isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None
            and _lan_address(str(address.ipv4_mapped)) is None)
    ):
        return None
    return address


def _discover(family: int) -> list[str]:
    try:
        records = socket.getaddrinfo(socket.gethostname(), None, family, socket.SOCK_STREAM)
    except OSError:
        return []
    addresses = {
        address for found_family, _kind, _protocol, _name, endpoint in records
        if found_family == family
        if (address := _lan_address(endpoint[0])) is not None
    }
    return [str(address) for address in sorted(addresses, key=int)]


def discover_lan_ipv4() -> list[str]:
    """Return distinct IPv4 adapter addresses, including virtual adapters."""
    return _discover(socket.AF_INET)


def discover_lan_ipv6() -> list[str]:
    """Return routable IPv6 adapter addresses, omitting scoped link-local URLs."""
    return _discover(socket.AF_INET6)


def _origin(host: str, port: int) -> str:
    return f"http://{'[' + host + ']' if ':' in host else host}:{port}"


def lan_urls_for_host(host: str, port: int) -> list[str]:
    """Return LAN origins for a numeric bind address or resolvable hostname."""
    if host == "0.0.0.0":
        addresses = discover_lan_ipv4()
    elif host == "::":
        addresses = discover_lan_ipv6()
    elif (address := _lan_address(host)) is not None:
        addresses = [str(address)]
    else:
        try:
            # Numeric loopback/unspecified/link-local addresses have no LAN URL.
            ipaddress.ip_address(host)
        except ValueError:
            try:
                records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            except OSError:
                return []
            resolved = {
                address for family, _kind, _protocol, _name, endpoint in records
                if family in (socket.AF_INET, socket.AF_INET6)
                if (address := _lan_address(endpoint[0])) is not None
            }
            addresses = [str(address) for address in sorted(resolved, key=lambda item: (item.version, int(item)))]
        else:
            addresses = []
    return [_origin(address, port) for address in addresses]


def lan_urls(listener: socket.socket) -> list[str]:
    """Advertise only the addresses served by a listener's actual binding."""
    if listener.family not in (socket.AF_INET, socket.AF_INET6):
        return []
    try:
        host, port = listener.getsockname()[:2]
    except OSError:
        return []
    urls = lan_urls_for_host(host, port)
    # A caller may supply a dual-stack IPv6 listener. Our portable launcher
    # uses IPv6-only sockets, but this helper also reflects external listeners.
    if listener.family == socket.AF_INET6 and host == "::":
        try:
            dual_stack = listener.getsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY) == 0
        except OSError:
            dual_stack = False
        if dual_stack:
            urls.extend(lan_urls_for_host("0.0.0.0", port))
    return urls
