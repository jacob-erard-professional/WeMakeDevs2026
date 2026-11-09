"""SSRF-guarded fetch for organizer-supplied schedule URLs.

The API fetches schedule URLs itself (the deterministic adapters need the raw bytes), so this
module is the only place that may open an outbound connection on behalf of a user-supplied URL.
Rules, from `docs/schedule-formats.md`:

- `https` only, port 443, no userinfo. `webcal://` is rewritten to `https://` by the caller.
- The hostname is resolved first and every address must be globally routable. The connection is
  then made to that vetted address (pinned) while TLS SNI and `Host` keep the hostname, so a DNS
  rebinding between check and connect cannot swap the target.
- Redirects are never followed automatically. Up to 3 hops are followed by hand, each re-checked.
- 5 s connect, 20 s total, body streamed and aborted past 10 MiB.
"""

from __future__ import annotations

import ipaddress
import socket
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpcore

MAX_FETCH_BYTES = 10 * 1024 * 1024
MAX_REDIRECTS = 3
CONNECT_TIMEOUT = 5.0
TOTAL_TIMEOUT = 20.0
USER_AGENT = "WeMakeDevs2026-schedule-import/1.0"


class UnsafeUrlError(ValueError):
    """The URL was rejected by the SSRF policy. The message is safe to show to the organizer."""


class FetchError(RuntimeError):
    """The remote server misbehaved (status, size, timeout). Safe to show to the organizer."""


@dataclass(frozen=True)
class Fetched:
    url: str
    content_type: str
    body: bytes


def normalize_url(url: str) -> str:
    """Rewrite `webcal://` to `https://` and validate scheme, port and userinfo."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme == "webcal":
        scheme = "https"
    if scheme != "https":
        raise UnsafeUrlError("Only https:// schedule URLs are supported")
    if not parts.hostname:
        raise UnsafeUrlError("The schedule URL has no host")
    if parts.username is not None or parts.password is not None:
        raise UnsafeUrlError("Credentials in the schedule URL are not supported")
    if parts.port not in (None, 443):
        raise UnsafeUrlError("Only port 443 is supported for schedule URLs")
    host = parts.hostname.lower().rstrip(".")
    if host in {"localhost"} or host.endswith(".localhost") or host.endswith(".local"):
        raise UnsafeUrlError("The schedule URL must point at a public host")
    return urlunsplit((scheme, host, parts.path or "/", parts.query, ""))


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def resolve_public_address(host: str) -> str:
    """Resolve `host` and return one vetted address. Any non-global result rejects the host."""
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not _is_public(host):
            raise UnsafeUrlError("The schedule URL must point at a public host")
        return host
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError(f"Could not resolve {host}") from exc
    addresses = [info[4][0] for info in infos]
    if not addresses:
        raise FetchError(f"Could not resolve {host}")
    for address in addresses:
        if not _is_public(address):
            raise UnsafeUrlError("The schedule URL must point at a public host")
    # Prefer IPv4 when both exist: fewer surprises on single-stack pods.
    for address in addresses:
        if ipaddress.ip_address(address).version == 4:
            return address
    return addresses[0]


class _PinnedBackend(httpcore.SyncBackend):
    """Connect to a pre-vetted IP while httpcore keeps the hostname for SNI/`Host`."""

    def __init__(self, host: str, address: str) -> None:
        super().__init__()
        self._host = host
        self._address = address

    def connect_tcp(  # type: ignore[override]
        self, host: str, port: int, timeout=None, local_address=None, socket_options=None
    ):
        if host != self._host or port != 443:
            raise UnsafeUrlError("Refusing to connect outside the vetted origin")
        return super().connect_tcp(
            self._address, port, timeout=timeout, local_address=None, socket_options=None
        )


def _fetch_once(url: str, deadline: float) -> tuple[int, dict[str, str], bytes]:
    parts = urlsplit(url)
    host = parts.hostname or ""
    address = resolve_public_address(host)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise FetchError("Fetching the schedule took too long")
    timeouts = {
        "connect": min(CONNECT_TIMEOUT, remaining),
        "read": remaining,
        "write": remaining,
        "pool": remaining,
    }
    headers = [
        (b"host", host.encode("idna")),
        (b"user-agent", USER_AGENT.encode()),
        (b"accept", b"text/calendar, application/json, application/xml, text/xml, text/html, */*"),
    ]
    with httpcore.ConnectionPool(
        network_backend=_PinnedBackend(host, address), max_connections=1, retries=0
    ) as pool:
        try:
            with pool.stream(b"GET", url, headers=headers, extensions={"timeout": timeouts}) as r:
                response_headers = {
                    k.decode("latin-1").lower(): v.decode("latin-1") for k, v in r.headers
                }
                declared = response_headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > MAX_FETCH_BYTES:
                    raise FetchError("The schedule is larger than 10 MiB")
                chunks: list[bytes] = []
                size = 0
                for chunk in r.iter_stream():
                    size += len(chunk)
                    if size > MAX_FETCH_BYTES:
                        raise FetchError("The schedule is larger than 10 MiB")
                    if time.monotonic() > deadline:
                        raise FetchError("Fetching the schedule took too long")
                    chunks.append(chunk)
                return r.status, response_headers, b"".join(chunks)
        except httpcore.TimeoutException as exc:
            raise FetchError("Fetching the schedule took too long") from exc
        except httpcore.NetworkError as exc:
            raise FetchError(f"Could not connect to {host}") from exc
        except httpcore.ProtocolError as exc:
            raise FetchError(f"{host} returned an invalid response") from exc


def safe_fetch(url: str) -> Fetched:
    """GET `url` under the SSRF policy, following at most 3 hand-checked redirects."""
    current = normalize_url(url)
    deadline = time.monotonic() + TOTAL_TIMEOUT
    for _ in range(MAX_REDIRECTS + 1):
        status, headers, body = _fetch_once(current, deadline)
        if status in (301, 302, 303, 307, 308):
            location = headers.get("location")
            if not location:
                raise FetchError("The schedule URL redirected without a destination")
            current = normalize_url(urljoin(current, location))
            continue
        if status != 200:
            raise FetchError(f"The schedule URL returned HTTP {status}")
        content_type = headers.get("content-type", "").split(";")[0].strip().lower()
        return Fetched(url=current, content_type=content_type, body=body)
    raise FetchError("The schedule URL redirected too many times")
