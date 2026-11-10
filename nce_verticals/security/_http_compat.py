"""
HTTP client compatibility layer: uses `httpx` when installed, and falls back
to a zero-dependency `urllib.request` async wrapper with explicit <5s timeouts.
"""

from __future__ import annotations

import asyncio
import json as _json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

try:
    import httpx as httpx  # type: ignore[no-redef]
except ImportError:

    class _CompatResponse:
        def __init__(self, status_code: int, body: bytes) -> None:
            self.status_code = status_code
            self.content = body
            self.text = body.decode("utf-8", errors="replace")

        def json(self) -> Any:
            return _json.loads(self.text) if self.text else {}

    class Timeout:
        def __init__(
            self,
            connect: float = 4.0,
            read: float = 5.0,
            write: float = 4.0,
            pool: float = 4.0,
        ) -> None:
            self.timeout = max(connect, read)

    class AsyncClient:
        def __init__(self, timeout: Timeout | float | None = None) -> None:
            self._timeout = (
                timeout.timeout if isinstance(timeout, Timeout) else float(timeout or 5.0)
            )

        async def __aenter__(self) -> AsyncClient:
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            return None

        async def request(
            self,
            method: str,
            url: str,
            *,
            params: dict[str, Any] | None = None,
            data: dict[str, Any] | None = None,
            json: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None,
        ) -> _CompatResponse:
            full_url = url
            if params:
                qs = urllib.parse.urlencode(params)
                sep = "&" if "?" in full_url else "?"
                full_url = f"{full_url}{sep}{qs}"

            req_headers = dict(headers or {})
            body_bytes: bytes | None = None
            if json is not None:
                body_bytes = _json.dumps(json).encode("utf-8")
                req_headers.setdefault("Content-Type", "application/json")
            elif data is not None:
                body_bytes = urllib.parse.urlencode(data).encode("utf-8")
                req_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

            def _sync_call() -> _CompatResponse:
                req = urllib.request.Request(
                    full_url,
                    data=body_bytes,
                    headers=req_headers,
                    method=method.upper(),
                )
                try:
                    with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                        return _CompatResponse(resp.status, resp.read())
                except urllib.error.HTTPError as err:
                    return _CompatResponse(err.code, err.read())

            return await asyncio.to_thread(_sync_call)

        async def get(self, url: str, **kwargs: Any) -> _CompatResponse:
            return await self.request("GET", url, **kwargs)

        async def post(self, url: str, **kwargs: Any) -> _CompatResponse:
            return await self.request("POST", url, **kwargs)

    class _HttpxShim:
        Timeout = Timeout
        AsyncClient = AsyncClient

    httpx = _HttpxShim()  # type: ignore[assignment]
