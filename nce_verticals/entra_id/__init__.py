"""
nce_verticals/entra_id
======================
Microsoft Entra ID (Azure AD) Identification Point & Company Allowlist Gate.

Ensures zero-trust identity verification and company Microsoft Entra Security Group /
Enterprise App Role allowlist enforcement even when NCE is only used by connecting an
LLM (such as Claude Desktop via MCP stdio/SSE) on a user's PC.
"""

from nce_verticals.entra_id.auth import (
    EntraConfig,
    EntraIDAuthenticator,
    EntraPrincipal,
    EntraVerificationError,
)
from nce_verticals.entra_id.guard import (
    EntraSecurityGate,
    get_global_entra_gate,
    require_entra_identity,
)

__all__ = [
    "EntraConfig",
    "EntraIDAuthenticator",
    "EntraPrincipal",
    "EntraSecurityGate",
    "EntraVerificationError",
    "get_global_entra_gate",
    "require_entra_identity",
]
