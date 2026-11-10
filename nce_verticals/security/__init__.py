"""
nce_verticals/security package.
"""

from nce_verticals.security.entra_id import (
    ALLOWED_JWT_ALGORITHMS,
    DEFAULT_GRAPH_BASE_URL,
    EntraConfig,
    EntraIDAuthenticator,
    EntraPrincipal,
    EntraSecurityGate,
    EntraVerificationError,
    get_global_entra_gate,
    require_entra_identity,
)

__all__ = [
    "ALLOWED_JWT_ALGORITHMS",
    "DEFAULT_GRAPH_BASE_URL",
    "EntraConfig",
    "EntraIDAuthenticator",
    "EntraPrincipal",
    "EntraSecurityGate",
    "EntraVerificationError",
    "get_global_entra_gate",
    "require_entra_identity",
]
