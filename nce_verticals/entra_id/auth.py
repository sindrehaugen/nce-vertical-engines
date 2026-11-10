"""
nce_verticals/entra_id/auth.py
==============================
Compatibility shim re-exporting from nce_verticals.security.entra_id.
"""

from __future__ import annotations

from nce_verticals.security.entra_id import (
    ALLOWED_JWT_ALGORITHMS,
    DEFAULT_GRAPH_BASE_URL,
    HTTP_TIMEOUT,
    EntraConfig,
    EntraIDAuthenticator,
    EntraPrincipal,
    EntraVerificationError,
    _decode_jwt_header_unverified,
    _decode_jwt_payload_unverified,
)

__all__ = [
    "ALLOWED_JWT_ALGORITHMS",
    "DEFAULT_GRAPH_BASE_URL",
    "HTTP_TIMEOUT",
    "EntraConfig",
    "EntraIDAuthenticator",
    "EntraPrincipal",
    "EntraVerificationError",
    "_decode_jwt_header_unverified",
    "_decode_jwt_payload_unverified",
]
