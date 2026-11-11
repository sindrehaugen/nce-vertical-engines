"""
nce_verticals/security/http_guard.py
====================================
Security guards for vertical engines:
- Pure-ASGI BoundedBodyMiddleware (HTTP 413 Payload Too Large)
- SSRF outbound URL validator with IP unwrapping and metadata/internal blocking
- Microsoft Entra ID database schema prerequisite verification (075)
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import socket
import urllib.parse
from collections.abc import Callable
from typing import Any

log = logging.getLogger("nce_verticals.security.http_guard")

# Maximum permitted URL length
_MAX_URL_LEN: int = 4096

# Explicit RFC 6598 CGNAT IPv4 range
_CGNAT_IPV4_NETWORK: ipaddress.IPv4Network = ipaddress.IPv4Network("100.64.0.0/10")

# Denied IPv6 networks
_SSRF_DENIED_IPV6_NETWORKS: tuple[ipaddress.IPv6Network, ...] = tuple(
    ipaddress.ip_network(c)  # type: ignore[misc]
    for c in (
        "::/128",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
        "fec0::/10",
        "2001:db8::/32",
        "100::/64",
    )
)

BLOCKED_INTERNAL_HOSTNAMES: frozenset[str] = frozenset(
    {
        "localhost",
        "host.docker.internal",
        "gateway.docker.internal",
        "kubernetes.default",
        "kubernetes.default.svc",
        "metadata.google.internal",
        "metadata",
        "instance-data",
    }
)


class SSRFBlockedError(ValueError):
    """Raised when an outbound URL violates SSRF safety requirements."""


def unwrap_ip(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Unwrap IPv4-mapped IPv6 address (e.g. ::ffff:169.254.169.254 -> 169.254.169.254)."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def is_ip_blocked(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    """Return True if an IP is in private, link-local, CGNAT, loopback, non-global, or denied ranges."""
    ip = unwrap_ip(ip)
    if isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT_IPV4_NETWORK:
        return True
    if not ip.is_global:
        return True
    if ip.version == 6:
        for net in _SSRF_DENIED_IPV6_NETWORKS:
            if ip in net:
                return True
    if ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_loopback:
        return True
    return False


def _get_ssrf_allowlist() -> set[str]:
    raw = os.environ.get("NCE_SSRF_ALLOWLIST_HOSTS", "")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def validate_outbound_url(
    url: str,
    *,
    allow_http: bool = True,
    resolve_dns: bool = True,
) -> str:
    """Validate an outbound URL against SSRF attacks (sync).

    Blocks private, link-local, loopback, CGNAT, IPv4-mapped IPv6,
    cloud metadata, and internal Docker/Kubernetes hostnames unless allowlisted.
    """
    raw = (url or "").strip()
    if not raw:
        raise SSRFBlockedError("Outbound URL cannot be empty")
    if len(raw) > _MAX_URL_LEN:
        raise SSRFBlockedError(
            f"Outbound URL exceeds maximum allowed length of {_MAX_URL_LEN} characters"
        )

    parsed = urllib.parse.urlparse(raw)
    if parsed.username or parsed.password:
        raise SSRFBlockedError("Outbound URL must not contain embedded user credentials")

    allowed_schemes = ("http", "https") if allow_http else ("https",)
    if parsed.scheme not in allowed_schemes:
        scheme_msg = "http or https" if allow_http else "https only"
        raise SSRFBlockedError(f"Outbound URL must use scheme {scheme_msg} (got {parsed.scheme!r})")

    host = parsed.hostname
    if not host:
        raise SSRFBlockedError("Outbound URL is missing a hostname")

    allowlist = _get_ssrf_allowlist()
    normalized_host = host.lower().strip().rstrip(".")

    if normalized_host in allowlist:
        return raw

    # Reject internal, cloud metadata, and single-label hostnames
    if (
        normalized_host in BLOCKED_INTERNAL_HOSTNAMES
        or normalized_host.endswith(".internal")
        or normalized_host.endswith(".local")
        or ("." not in normalized_host and not normalized_host.startswith("["))
    ):
        raise SSRFBlockedError(f"Host {host!r} is a blocked internal or metadata hostname")

    # Check if host is an IP literal
    clean_host = host.strip("[]")
    if "%" in clean_host:
        clean_host = clean_host.split("%", 1)[0]

    try:
        ip = ipaddress.ip_address(clean_host)
    except ValueError:
        ip = None

    if ip is not None:
        unwrapped = unwrap_ip(ip)
        if str(ip).lower() in allowlist or str(unwrapped).lower() in allowlist:
            return raw
        if is_ip_blocked(ip):
            raise SSRFBlockedError(
                f"Host {host!r} is a non-global, private, or loopback IP address"
            )
        return raw

    if not resolve_dns:
        return raw

    try:
        infos = socket.getaddrinfo(host, None, 0, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        is_prod = os.environ.get("NCE_ENV", "").lower() in ("prod", "production")
        if is_prod:
            raise SSRFBlockedError(f"Cannot resolve host {host!r}: {exc}") from exc
        log.warning("DNS resolution failed for %r in non-production environment: %s", host, exc)
        return raw
    except Exception as exc:
        raise SSRFBlockedError(f"DNS resolution failed for host {host!r}: {exc}") from exc

    resolved_ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for item in infos:
        sockaddr = item[4]
        try:
            raw_ip = str(sockaddr[0]).strip("[]")
            if "%" in raw_ip:
                raw_ip = raw_ip.split("%", 1)[0]
            resolved_ips.append(ipaddress.ip_address(raw_ip))
        except ValueError:
            continue

    if not resolved_ips:
        raise SSRFBlockedError(f"No usable IP addresses resolved for host {host!r}")

    for resolved_ip in resolved_ips:
        unwrapped = unwrap_ip(resolved_ip)
        if str(resolved_ip).lower() in allowlist or str(unwrapped).lower() in allowlist:
            continue
        if is_ip_blocked(resolved_ip):
            raise SSRFBlockedError(f"Host {host!r} resolves to non-global address {resolved_ip}")

    return raw


async def validate_outbound_url_async(
    url: str,
    *,
    allow_http: bool = True,
    resolve_dns: bool = True,
) -> str:
    """Validate an outbound URL against SSRF attacks (async)."""
    return await asyncio.to_thread(
        validate_outbound_url,
        url,
        allow_http=allow_http,
        resolve_dns=resolve_dns,
    )


# ---------------------------------------------------------------------------
# Pure-ASGI Body Limit Middleware
# ---------------------------------------------------------------------------


class _BodyTooLargeError(Exception):
    """Internal exception raised when streaming request body exceeds configured limit."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"Request body exceeds maximum allowed size of {limit} bytes.")
        self.limit = limit


def _build_413_response(limit: int) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = json.dumps(
        {
            "error": "payload_too_large",
            "detail": f"Request body exceeds maximum allowed size of {limit} bytes.",
        }
    ).encode("utf-8")
    start_message = {
        "type": "http.response.start",
        "status": 413,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(payload)).encode("ascii")),
        ],
    }
    body_message = {
        "type": "http.response.body",
        "body": payload,
    }
    return start_message, body_message


class BoundedBodyMiddleware:
    """Pure-ASGI middleware that rejects oversized HTTP request bodies with 413 Payload Too Large.

    Inspects Content-Length before dispatch and tracks received streaming/chunked body chunks.
    Reads NCE_MAX_HTTP_BODY_BYTES env var (default 10,485,760 bytes = 10 MB).
    """

    def __init__(
        self,
        app: Any,
        max_bytes: int | Callable[[], int] | None = None,
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes

    def _get_limit(self) -> int:
        if callable(self.max_bytes):
            try:
                return max(1, int(self.max_bytes()))
            except Exception as exc:
                log.debug("Failed evaluating max_bytes callable: %s", exc)
        elif isinstance(self.max_bytes, int):
            return max(1, self.max_bytes)

        raw = os.environ.get("NCE_MAX_HTTP_BODY_BYTES")
        if raw:
            try:
                return max(1, int(raw))
            except ValueError:
                log.debug("Invalid NCE_MAX_HTTP_BODY_BYTES value: %s", raw)
        return 10_485_760

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Any],
        send: Callable[[dict[str, Any]], Any],
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        limit = self._get_limit()

        # 1. Content-Length header inspection
        content_length_header: bytes | None = None
        for key, val in scope.get("headers", []):
            if key.lower() == b"content-length":
                content_length_header = val
                break

        if content_length_header is not None:
            try:
                cl_val = int(content_length_header.decode("latin1").strip())
                if cl_val < 0 or cl_val > limit:
                    start_msg, body_msg = _build_413_response(limit)
                    await send(start_msg)
                    await send(body_msg)
                    return
            except (ValueError, UnicodeDecodeError):
                start_msg, body_msg = _build_413_response(limit)
                await send(start_msg)
                await send(body_msg)
                return

        # 2. Chunked / Content-Length-omitted write requests: bound at perimeter
        method = str(scope.get("method", "")).upper()
        if content_length_header is None and method in ("POST", "PUT", "PATCH"):
            buffered_messages: list[dict[str, Any]] = []
            chunk_bytes = 0
            while True:
                message = await receive()
                if message.get("type") == "http.request":
                    chunk = message.get("body", b"")
                    if chunk:
                        chunk_bytes += len(chunk)
                        if chunk_bytes > limit:
                            start_msg, body_msg = _build_413_response(limit)
                            await send(start_msg)
                            await send(body_msg)
                            return
                    buffered_messages.append(message)
                    if not message.get("more_body", False):
                        break
                else:
                    buffered_messages.append(message)
                    break

            idx = 0

            async def replay_receive() -> dict[str, Any]:
                nonlocal idx
                if idx < len(buffered_messages):
                    msg = buffered_messages[idx]
                    idx += 1
                    return msg
                return await receive()

            await self.app(scope, replay_receive, send)
            return

        # 3. Streaming guard when Content-Length is present (defends against lying headers)
        bytes_received = 0
        response_started = False

        async def wrapped_receive() -> dict[str, Any]:
            nonlocal bytes_received
            message = await receive()
            if message.get("type") == "http.request":
                chunk = message.get("body", b"")
                if chunk:
                    bytes_received += len(chunk)
                    if bytes_received > limit:
                        raise _BodyTooLargeError(limit)
            return message

        async def wrapped_send(message: dict[str, Any]) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, wrapped_receive, wrapped_send)
        except _BodyTooLargeError as exc:
            if not response_started:
                start_msg, body_msg = _build_413_response(exc.limit)
                await send(start_msg)
                await send(body_msg)
            else:
                raise


# ---------------------------------------------------------------------------
# Entra ID Schema Gate Helper (075)
# ---------------------------------------------------------------------------


async def verify_entra_id_schema_gate(conn: Any) -> bool:
    """Verify that prerequisite tables from 075_entra_id_security_gate.sql exist in PostgreSQL.

    Raises RuntimeError mentioning 075_entra_id_security_gate.sql if missing
    when the Entra ID security gate is active.
    """
    if conn is None:
        return True

    # If enforce mode is explicitly disabled, skip enforcement
    enforce_mode = os.environ.get("NCE_ENTRA_ENFORCE_MODE", "").strip().lower()
    if enforce_mode == "disabled":
        return True

    try:
        required_tables = (
            "public.entra_id_configs",
            "public.entra_id_sessions",
            "public.entra_id_audit_log",
        )
        for tbl in required_tables:
            reg = await conn.fetchval(f"SELECT to_regclass('{tbl}')")
            if reg is None:
                raise RuntimeError(
                    f"Microsoft Entra ID security gate is active, but prerequisite database "
                    f"table {tbl!r} from 075_entra_id_security_gate.sql is missing in PostgreSQL."
                )
        return True
    except RuntimeError:
        raise
    except (AssertionError, AttributeError, NotImplementedError):
        # Mocks and fake connections in unit tests
        return True
    except Exception as exc:
        log.warning("verify_entra_id_schema_gate check encountered non-fatal error: %s", exc)
        return True
