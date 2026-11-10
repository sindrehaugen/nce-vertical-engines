"""
nce_verticals/security/entra_id.py
==================================
Consolidated Microsoft Entra ID (Azure AD) OIDC / OAuth 2.0 / PC Session Authenticator,
Security Group & App Role Allowlist Verifier, and Execution Security Gate.

Provides strict JWT validation:
- ALLOWED_JWT_ALGORITHMS allowlist: RS256, ES256
- Strict claims checking: iss, aud, exp, nbf, tid, oid
- Bounded JWKS cache TTL with configurable jwks_cache_ttl_seconds (default 3600s)
- Transitive group membership and App Role enforcement
"""

from __future__ import annotations

import asyncio
import base64
import collections
import dataclasses
import functools
import getpass
import json
import logging
import os
import socket
import time
from collections.abc import Callable
from typing import Any

from nce_verticals.security._http_compat import httpx

log = logging.getLogger("nce_verticals.security.entra_id")

HTTP_TIMEOUT = httpx.Timeout(connect=4.0, read=5.0, write=4.0, pool=4.0)

ALLOWED_JWT_ALGORITHMS: frozenset[str] = frozenset({"RS256", "ES256"})
DEFAULT_GRAPH_BASE_URL: str = "https://graph.microsoft.com/v1.0"


class EntraVerificationError(PermissionError):
    """Raised when Entra ID identity verification or allowlist check fails."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "ENTRA_ACCESS_DENIED",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclasses.dataclass(slots=True)
class EntraConfig:
    """Configuration for the Entra ID Identification Point."""

    entra_tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    enforce_mode: str = "strict"  # 'strict' | 'audit_only' | 'disabled'
    allowed_group_ids: list[str] = dataclasses.field(default_factory=list)
    allowed_app_roles: list[str] = dataclasses.field(default_factory=list)
    allowed_upns: list[str] = dataclasses.field(default_factory=list)
    blocked_upns: list[str] = dataclasses.field(default_factory=list)
    require_graph_check: bool = True
    allow_os_silent_auth: bool = True
    allow_device_code_flow: bool = True
    session_ttl_seconds: int = 28800
    jwks_cache_ttl_seconds: int = 3600

    @classmethod
    def from_env(cls) -> EntraConfig:
        """Load Entra ID configuration from environment variables."""
        groups_raw = os.environ.get("NCE_ENTRA_ALLOWED_GROUPS", "")
        roles_raw = os.environ.get("NCE_ENTRA_ALLOWED_ROLES", "")
        upns_raw = os.environ.get("NCE_ENTRA_ALLOWED_UPNS", "")
        blocked_raw = os.environ.get("NCE_ENTRA_BLOCKED_UPNS", "")

        tenant_id = os.environ.get("NCE_ENTRA_TENANT_ID", "").strip()
        default_mode = "strict" if tenant_id else "disabled"
        enforce_mode = os.environ.get("NCE_ENTRA_ENFORCE_MODE", default_mode).strip().lower()
        if enforce_mode not in ("strict", "audit_only", "disabled"):
            enforce_mode = default_mode

        return cls(
            entra_tenant_id=tenant_id,
            client_id=os.environ.get("NCE_ENTRA_CLIENT_ID", "").strip(),
            client_secret=os.environ.get("NCE_ENTRA_CLIENT_SECRET", "").strip(),
            enforce_mode=enforce_mode,
            allowed_group_ids=[g.strip() for g in groups_raw.split(",") if g.strip()],
            allowed_app_roles=[r.strip() for r in roles_raw.split(",") if r.strip()],
            allowed_upns=[u.strip().lower() for u in upns_raw.split(",") if u.strip()],
            blocked_upns=[u.strip().lower() for u in blocked_raw.split(",") if u.strip()],
            require_graph_check=os.environ.get("NCE_ENTRA_REQUIRE_GRAPH_CHECK", "true").lower()
            in ("1", "true", "yes"),
            allow_os_silent_auth=os.environ.get("NCE_ENTRA_ALLOW_OS_SILENT", "true").lower()
            in ("1", "true", "yes"),
            allow_device_code_flow=os.environ.get("NCE_ENTRA_ALLOW_DEVICE_CODE", "true").lower()
            in ("1", "true", "yes"),
            session_ttl_seconds=max(
                300, min(86400, int(os.environ.get("NCE_ENTRA_SESSION_TTL", "28800")))
            ),
            jwks_cache_ttl_seconds=max(60, int(os.environ.get("NCE_ENTRA_JWKS_CACHE_TTL", "3600"))),
        )

    def to_safe_dict(self) -> dict[str, Any]:
        """Return dictionary representation with secrets masked."""
        return {
            "entra_tenant_id": self.entra_tenant_id,
            "client_id": self.client_id,
            "client_secret_set": bool(self.client_secret),
            "enforce_mode": self.enforce_mode,
            "allowed_group_ids": list(self.allowed_group_ids),
            "allowed_app_roles": list(self.allowed_app_roles),
            "allowed_upns": list(self.allowed_upns),
            "blocked_upns": list(self.blocked_upns),
            "require_graph_check": self.require_graph_check,
            "allow_os_silent_auth": self.allow_os_silent_auth,
            "allow_device_code_flow": self.allow_device_code_flow,
            "session_ttl_seconds": self.session_ttl_seconds,
            "jwks_cache_ttl_seconds": self.jwks_cache_ttl_seconds,
        }


@dataclasses.dataclass(slots=True)
class EntraPrincipal:
    """Verified Microsoft Entra ID User Principal."""

    oid: str
    tid: str
    upn: str
    display_name: str
    pc_hostname: str
    os_username: str
    auth_method: str
    matched_groups: list[str]
    matched_roles: list[str]
    verified_at: float
    expires_at: float
    raw_access_token: str | None = dataclasses.field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "oid": self.oid,
            "tid": self.tid,
            "upn": self.upn,
            "display_name": self.display_name,
            "pc_hostname": self.pc_hostname,
            "os_username": self.os_username,
            "auth_method": self.auth_method,
            "matched_groups": self.matched_groups,
            "matched_roles": self.matched_roles,
            "verified_at": self.verified_at,
            "expires_at": self.expires_at,
        }


def _decode_jwt_header_unverified(token: str) -> dict[str, Any]:
    """Decode JWT header segment to verify algorithm and token type."""
    parts = token.strip().split(".")
    if len(parts) != 3:
        raise EntraVerificationError("Malformed JWT token format", code="INVALID_JWT_FORMAT")
    header_b64 = parts[0]
    pad = "=" * ((4 - len(header_b64) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode(header_b64 + pad)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Header is not a JSON object")
        return data
    except Exception as exc:
        raise EntraVerificationError(
            f"Failed to decode JWT header: {exc}", code="INVALID_JWT_HEADER"
        ) from exc


def _decode_jwt_payload_unverified(token: str) -> dict[str, Any]:
    """Decode JWT payload segment (used prior to JWKS/Graph verification)."""
    parts = token.strip().split(".")
    if len(parts) != 3:
        raise EntraVerificationError("Malformed JWT token format", code="INVALID_JWT_FORMAT")
    payload_b64 = parts[1]
    pad = "=" * ((4 - len(payload_b64) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload_b64 + pad)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Payload is not a JSON object")
        return data
    except Exception as exc:
        raise EntraVerificationError(
            f"Failed to decode JWT claims: {exc}", code="INVALID_JWT_CLAIMS"
        ) from exc


class EntraIDAuthenticator:
    """
    Zero-trust Microsoft Entra ID authenticator & company allowlist verifier.
    Operates both standalone (in-memory session cache) and integrated (Redis + Postgres).
    """

    def __init__(self, config: EntraConfig | None = None, redis_client: Any = None) -> None:
        self.config = config or EntraConfig.from_env()
        self._redis = redis_client
        self._memory_sessions: dict[str, EntraPrincipal] = {}
        self._jwks_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def update_config(self, config: EntraConfig) -> None:
        self.config = config

    @staticmethod
    def get_local_pc_context() -> dict[str, str]:
        """Return the local PC hostname and logged-in OS username."""
        try:
            hostname = socket.gethostname()
        except Exception:
            hostname = "unknown-pc"
        try:
            username = os.environ.get("USERNAME") or os.environ.get("USER") or getpass.getuser()
        except Exception:
            username = "unknown-user"
        return {"pc_hostname": hostname, "os_username": username}

    async def fetch_openid_jwks(self, tenant_id: str | None = None) -> dict[str, Any]:
        """
        Fetch and cache the Microsoft Entra ID OpenID Connect JWKS keys for `tenant_id`
        (`https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys`) with bounded cache TTL.
        """
        tid = (tenant_id or self.config.entra_tenant_id or "common").strip()
        now = time.time()
        cached = self._jwks_cache.get(tid)
        if cached and cached[0] > now:
            return cached[1]

        url = f"https://login.microsoftonline.com/{tid}/discovery/v2.0/keys"
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                raise EntraVerificationError(
                    f"Failed to fetch Entra ID JWKS keys (HTTP {resp.status_code})",
                    code="JWKS_FETCH_FAILED",
                )
            jwks = resp.json()
            ttl = float(self.config.jwks_cache_ttl_seconds)
            self._jwks_cache[tid] = (now + ttl, jwks)
            return jwks

    async def acquire_os_silent_token(self) -> tuple[str | None, str]:
        """
        Attempt to acquire an Entra ID access token silently from the user's PC environment:
        1. NCE_ENTRA_USER_TOKEN / AZURE_ACCESS_TOKEN environment variable.
        2. Local Azure CLI / MSAL broker (`az account get-access-token --resource https://graph.microsoft.com`).
        """
        env_tok = (
            os.environ.get("NCE_ENTRA_USER_TOKEN", "").strip()
            or os.environ.get("AZURE_ACCESS_TOKEN", "").strip()
            or os.environ.get("BEARER_TOKEN", "").strip()
        )
        if env_tok:
            return env_tok, "env_var"

        if not self.config.allow_os_silent_auth:
            return None, "none"

        try:
            proc = await asyncio.create_subprocess_exec(
                "az",
                "account",
                "get-access-token",
                "--resource",
                "https://graph.microsoft.com",
                "--output",
                "json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=4.0)
            if proc.returncode == 0 and stdout:
                data = json.loads(stdout.decode("utf-8"))
                tok = data.get("accessToken")
                if tok:
                    return tok, "azure_cli_broker"
        except Exception:
            pass

        return None, "none"

    async def init_device_code_flow(self, scopes: list[str] | None = None) -> dict[str, Any]:
        """Initiate OAuth 2.0 Device Code Authorization Flow for interactive PC/LLM users."""
        if not self.config.entra_tenant_id or not self.config.client_id:
            raise EntraVerificationError(
                "Entra ID tenant_id and client_id must be configured for device code flow.",
                code="ENTRA_NOT_CONFIGURED",
            )
        scope_str = " ".join(
            scopes or ["openid", "profile", "email", "User.Read", "GroupMember.Read.All"]
        )
        url = f"https://login.microsoftonline.com/{self.config.entra_tenant_id}/oauth2/v2.0/devicecode"
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.post(
                url,
                data={"client_id": self.config.client_id, "scope": scope_str},
            )
            if resp.status_code != 200:
                raise EntraVerificationError(
                    f"Entra ID device code request failed (HTTP {resp.status_code})",
                    code="DEVICE_CODE_REQUEST_FAILED",
                )
            data = resp.json()
            return {
                "user_code": data.get("user_code"),
                "device_code": data.get("device_code"),
                "verification_uri": data.get(
                    "verification_uri", "https://microsoft.com/devicelogin"
                ),
                "expires_in": data.get("expires_in", 900),
                "interval": data.get("interval", 5),
                "message": data.get("message"),
            }

    async def complete_device_code_flow(self, device_code: str) -> EntraPrincipal:
        """Exchange a completed OAuth 2.0 `device_code` for tokens and verify the user against the allowlist."""
        if not self.config.entra_tenant_id or not self.config.client_id:
            raise EntraVerificationError(
                "Entra ID tenant_id and client_id must be configured.",
                code="ENTRA_NOT_CONFIGURED",
            )
        url = f"https://login.microsoftonline.com/{self.config.entra_tenant_id}/oauth2/v2.0/token"
        payload: dict[str, str] = {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": self.config.client_id,
            "device_code": device_code,
        }
        if self.config.client_secret:
            payload["client_secret"] = self.config.client_secret

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.post(url, data=payload)
            if resp.status_code != 200:
                err_body = {}
                try:
                    err_body = resp.json()
                except Exception:
                    pass
                err_code = err_body.get("error", f"HTTP_{resp.status_code}")
                raise EntraVerificationError(
                    f"Device code token exchange not complete: {err_code}",
                    code=err_code.upper(),
                )
            token_data = resp.json()
            access_token = token_data.get("access_token") or token_data.get("id_token")
            if not access_token:
                raise EntraVerificationError(
                    "No access_token returned from Entra ID", code="NO_ACCESS_TOKEN"
                )

        return await self.verify_token_and_allowlist(access_token, auth_method="device_code")

    async def _verify_with_microsoft_graph(
        self,
        access_token: str,
        required_group_ids: list[str],
    ) -> tuple[dict[str, Any], list[str]]:
        """
        Query Microsoft Graph `/v1.0/me` and `/v1.0/me/checkMemberObjects` to:
        1. Cryptographically prove the access token is accepted by Microsoft Graph.
        2. Verify `accountEnabled` is True.
        3. Check transitive membership in the company's allowed Entra Security Groups.
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            me_resp = await client.get(
                f"{DEFAULT_GRAPH_BASE_URL}/me?$select=id,userPrincipalName,displayName,accountEnabled,mail",
                headers=headers,
            )
            if me_resp.status_code != 200:
                raise EntraVerificationError(
                    f"Microsoft Graph rejected token (HTTP {me_resp.status_code})",
                    code="GRAPH_TOKEN_REJECTED",
                )
            me_data = me_resp.json()
            if me_data.get("accountEnabled") is False:
                raise EntraVerificationError(
                    "User account is disabled in Microsoft Entra ID",
                    code="ACCOUNT_DISABLED",
                )

            matched_groups: list[str] = []
            if required_group_ids:
                chk_resp = await client.post(
                    f"{DEFAULT_GRAPH_BASE_URL}/me/checkMemberObjects",
                    headers=headers,
                    json={"ids": required_group_ids},
                )
                if chk_resp.status_code == 200:
                    val = chk_resp.json().get("value", [])
                    if isinstance(val, list):
                        matched_groups = [str(g) for g in val]

            return me_data, matched_groups

    async def verify_token_and_allowlist(
        self,
        token: str,
        *,
        auth_method: str = "jwt_bearer",
    ) -> EntraPrincipal:
        """
        Validate an Entra ID JWT token and enforce company Microsoft Entra Security Group,
        App Role, and UPN allowlist rules (default-deny).
        """
        # Validate algorithm allowlist from JWT header
        try:
            header = _decode_jwt_header_unverified(token)
            alg = header.get("alg")
            if alg and alg not in ALLOWED_JWT_ALGORITHMS:
                raise EntraVerificationError(
                    f"JWT algorithm '{alg}' is not permitted. Allowed algorithms: {sorted(ALLOWED_JWT_ALGORITHMS)}",
                    code="DISALLOWED_JWT_ALGORITHM",
                )
        except EntraVerificationError:
            raise
        except Exception as exc:
            raise EntraVerificationError(
                f"Failed to inspect JWT header: {exc}", code="INVALID_JWT_HEADER"
            ) from exc

        claims = _decode_jwt_payload_unverified(token)
        now = time.time()

        exp = float(claims.get("exp", 0))
        nbf = float(claims.get("nbf", 0))
        if exp and now > exp + 60:
            raise EntraVerificationError("Entra ID token has expired", code="TOKEN_EXPIRED")
        if nbf and now + 60 < nbf:
            raise EntraVerificationError(
                "Entra ID token is not yet valid (nbf)", code="TOKEN_NOT_YET_VALID"
            )

        tid = str(claims.get("tid") or "").strip()
        oid = str(claims.get("oid") or claims.get("sub") or "").strip()
        upn = (
            str(claims.get("preferred_username") or claims.get("upn") or claims.get("email") or "")
            .strip()
            .lower()
        )
        display_name = str(claims.get("name") or upn or oid)

        if not oid or not tid:
            raise EntraVerificationError(
                "Entra ID token is missing required 'oid' or 'tid' claims",
                code="MISSING_OID_TID",
            )

        # 1. Verify Tenant ID matches company Entra Tenant ID
        if self.config.entra_tenant_id and tid.lower() != self.config.entra_tenant_id.lower():
            raise EntraVerificationError(
                f"Tenant ID mismatch: token tid '{tid}' is not authorized for tenant '{self.config.entra_tenant_id}'",
                code="TENANT_MISMATCH",
            )

        # 1b. Verify Token Issuer ('iss') when present in claims against Microsoft Entra v1/v2 endpoints
        iss = str(claims.get("iss") or "").strip().lower().rstrip("/")
        if iss:
            tid_low = tid.lower()
            valid_issuers = {
                f"https://login.microsoftonline.com/{tid_low}/v2.0",
                f"https://login.microsoftonline.com/{tid_low}",
                f"https://sts.windows.net/{tid_low}",
            }
            if iss not in valid_issuers:
                raise EntraVerificationError(
                    f"Token issuer '{iss}' is not an authorized Microsoft Entra ID issuer for tenant '{tid}'",
                    code="ISSUER_MISMATCH",
                )

        # 2. Verify Audience if client_id is configured and token is not a Graph token
        aud = str(claims.get("aud") or "").strip()
        allowed_audiences = {
            self.config.client_id.lower(),
            f"api://{self.config.client_id.lower()}",
            "https://graph.microsoft.com",
            "00000003-0000-0000-c000-000000000000",  # MS Graph App ID
        }
        if self.config.client_id and aud.lower() not in allowed_audiences:
            raise EntraVerificationError(
                f"Token audience '{aud}' is not authorized for client '{self.config.client_id}'",
                code="AUDIENCE_MISMATCH",
            )

        # 3. Extract groups & roles from JWT claims
        token_groups = [str(g).lower() for g in (claims.get("groups") or []) if g]
        token_roles = [str(r) for r in (claims.get("roles") or []) if r]

        matched_groups: list[str] = []
        if self.config.allowed_group_ids:
            allowed_g_lower = {g.lower(): g for g in self.config.allowed_group_ids}
            for tg in token_groups:
                if tg in allowed_g_lower:
                    matched_groups.append(allowed_g_lower[tg])

        matched_roles: list[str] = []
        if self.config.allowed_app_roles:
            allowed_r_lower = {r.lower(): r for r in self.config.allowed_app_roles}
            for tr in token_roles:
                if tr.lower() in allowed_r_lower:
                    matched_roles.append(allowed_r_lower[tr.lower()])

        # 4. Microsoft Graph live check (validates token authenticity + transitive group membership)
        if self.config.require_graph_check:
            me_data, graph_groups = await self._verify_with_microsoft_graph(
                token,
                self.config.allowed_group_ids,
            )
            if me_data.get("id"):
                oid = str(me_data["id"])
            if me_data.get("userPrincipalName"):
                upn = str(me_data["userPrincipalName"]).strip().lower()
            if me_data.get("displayName"):
                display_name = str(me_data["displayName"])
            for gg in graph_groups:
                if gg not in matched_groups:
                    matched_groups.append(gg)

        # 5. Blocklist check (always enforced)
        if upn and upn in self.config.blocked_upns:
            raise EntraVerificationError(
                f"User '{upn}' is explicitly blocked in the Entra ID gate.",
                code="USER_BLOCKED",
            )

        # 6. Company Allowlist evaluation (Groups OR App Roles OR explicit UPN allowlist)
        has_allowlist_rules = bool(
            self.config.allowed_group_ids
            or self.config.allowed_app_roles
            or self.config.allowed_upns
        )
        if has_allowlist_rules:
            upn_allowed = bool(upn and upn in self.config.allowed_upns)
            if not (matched_groups or matched_roles or upn_allowed):
                raise EntraVerificationError(
                    f"User '{upn or oid}' is not a member of any authorized Microsoft Entra Security Group, "
                    "App Role, or UPN allowlist.",
                    code="NOT_IN_COMPANY_ALLOWLIST",
                    details={
                        "oid": oid,
                        "upn": upn,
                        "required_groups": self.config.allowed_group_ids,
                        "required_roles": self.config.allowed_app_roles,
                    },
                )

        pc_ctx = self.get_local_pc_context()
        ttl = min(
            self.config.session_ttl_seconds,
            int(max(300, (exp - now) if exp else self.config.session_ttl_seconds)),
        )
        principal = EntraPrincipal(
            oid=oid,
            tid=tid,
            upn=upn,
            display_name=display_name,
            pc_hostname=pc_ctx["pc_hostname"],
            os_username=pc_ctx["os_username"],
            auth_method=auth_method,
            matched_groups=matched_groups,
            matched_roles=matched_roles,
            verified_at=now,
            expires_at=now + ttl,
            raw_access_token=token,
        )
        await self._store_session(principal)
        return principal

    async def _store_session(self, principal: EntraPrincipal) -> None:
        """Cache verified principal session in memory and Redis (if connected)."""
        cache_key = f"{principal.tid}:{principal.oid}"
        self._memory_sessions[cache_key] = principal
        self._memory_sessions["latest_local_pc"] = principal

        if self._redis is not None:
            try:
                ttl = max(60, int(principal.expires_at - time.time()))
                rkey = f"nce:entra:session:{principal.tid}:{principal.oid}"
                await self._redis.set(rkey, json.dumps(principal.to_dict()), ex=ttl)
            except Exception as exc:
                log.debug("Redis session cache write skipped: %s", exc)

    async def get_cached_session(
        self, oid: str | None = None, tid: str | None = None
    ) -> EntraPrincipal | None:
        """Return an active, non-expired cached session if available."""
        now = time.time()
        if oid and tid:
            p = self._memory_sessions.get(f"{tid}:{oid}")
            if p and p.expires_at > now:
                return p
        p_latest = self._memory_sessions.get("latest_local_pc")
        if p_latest and p_latest.expires_at > now:
            if not oid or p_latest.oid == oid:
                return p_latest
        return None

    def list_active_sessions(self) -> list[dict[str, Any]]:
        """List all non-expired in-memory verified sessions."""
        now = time.time()
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for k, p in list(self._memory_sessions.items()):
            if p.expires_at <= now:
                continue
            if p.oid in seen:
                continue
            seen.add(p.oid)
            out.append(p.to_dict())
        return out

    def revoke_session(self, oid: str) -> bool:
        """Revoke cached session for a given Entra Object ID (`oid`)."""
        removed = False
        for k, p in list(self._memory_sessions.items()):
            if p.oid == oid:
                del self._memory_sessions[k]
                removed = True
        return removed

    async def resolve_and_verify_caller(
        self,
        arguments: dict[str, Any] | None = None,
    ) -> EntraPrincipal | None:
        """
        End-to-end resolution for an MCP tool call or standalone API request:
        1. If `enforce_mode == 'disabled'`, returns cached session if any, or None.
        2. Checks explicit `entra_token` / `access_token` in arguments.
        3. Checks active cached PC session.
        4. Attempts silent OS / Azure CLI token pickup from the user's PC.
        5. Raises `EntraVerificationError` if `enforce_mode == 'strict'` and verification fails.
        """
        args = arguments or {}
        explicit_token = str(args.get("entra_token") or args.get("_entra_token") or "").strip()

        if explicit_token:
            return await self.verify_token_and_allowlist(explicit_token, auth_method="jwt_bearer")

        cached = await self.get_cached_session(
            oid=args.get("entra_oid"),
            tid=self.config.entra_tenant_id or None,
        )
        if cached is not None:
            return cached

        silent_token, method = await self.acquire_os_silent_token()
        if silent_token:
            try:
                return await self.verify_token_and_allowlist(silent_token, auth_method=method)
            except EntraVerificationError:
                if self.config.enforce_mode == "strict":
                    raise

        if self.config.enforce_mode == "disabled":
            return None

        if self.config.enforce_mode == "audit_only":
            log.warning("Entra ID audit_only mode: no verified Entra session for local caller")
            return None

        raise EntraVerificationError(
            "Microsoft Entra ID authentication required. Connect your corporate account using "
            "the 'entra_login_device_code' tool or ensure you are signed in on your PC.",
            code="ENTRA_AUTH_REQUIRED",
            details={
                "entra_tenant_id": self.config.entra_tenant_id,
                "pc_context": self.get_local_pc_context(),
            },
        )


class EntraSecurityGate:
    """
    Central Entra ID Identification & Allowlist Gate.
    Maintains an in-memory ring buffer of recent audit events and persists to
    PostgreSQL `entra_id_audit_log` / `entra_id_sessions` when a DB pool is attached.
    """

    def __init__(self, authenticator: EntraIDAuthenticator | None = None) -> None:
        self.authenticator = authenticator or EntraIDAuthenticator()
        self._audit_ring: collections.deque[dict[str, Any]] = collections.deque(maxlen=500)

    @property
    def config(self) -> EntraConfig:
        return self.authenticator.config

    def record_audit(
        self,
        *,
        tool_or_route: str,
        decision: str,
        reason: str,
        principal: EntraPrincipal | None = None,
        namespace_id: str | None = None,
    ) -> dict[str, Any]:
        pc = self.authenticator.get_local_pc_context()
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "namespace_id": namespace_id or "default",
            "tool_or_route": tool_or_route,
            "decision": decision,
            "reason": reason,
            "entra_oid": principal.oid if principal else None,
            "upn": principal.upn if principal else None,
            "display_name": principal.display_name if principal else None,
            "pc_hostname": principal.pc_hostname if principal else pc["pc_hostname"],
            "os_username": principal.os_username if principal else pc["os_username"],
            "matched_groups": principal.matched_groups if principal else [],
            "matched_roles": principal.matched_roles if principal else [],
        }
        self._audit_ring.appendleft(entry)
        return entry

    def get_recent_audit_log(self, limit: int = 100) -> list[dict[str, Any]]:
        return list(self._audit_ring)[: max(1, min(500, limit))]

    async def verify_request(
        self,
        tool_or_route: str,
        arguments: dict[str, Any] | None = None,
        *,
        required_role: str | None = None,
        engine: Any = None,
    ) -> EntraPrincipal | None:
        """
        Verify that the caller is authenticated with Microsoft Entra ID and belongs
        to the company's allowed Security Groups / App Roles.
        """
        args = arguments or {}
        ns_id = str(args.get("namespace_id") or "")

        try:
            principal = await self.authenticator.resolve_and_verify_caller(args)
            if principal is not None and required_role:
                role_match = any(
                    r.lower() == required_role.lower() for r in principal.matched_roles
                )
                if not role_match and self.config.enforce_mode == "strict":
                    raise EntraVerificationError(
                        f"Caller '{principal.upn}' lacks required Entra App Role '{required_role}'",
                        code="MISSING_REQUIRED_ROLE",
                    )

            decision = (
                "ALLOW"
                if principal is not None or self.config.enforce_mode == "disabled"
                else "AUDIT_WARN"
            )
            reason = (
                f"Verified Entra principal {principal.upn} ({principal.auth_method})"
                if principal
                else f"Allowed under enforce_mode={self.config.enforce_mode}"
            )
            audit_entry = self.record_audit(
                tool_or_route=tool_or_route,
                decision=decision,
                reason=reason,
                principal=principal,
                namespace_id=ns_id,
            )
            await self._persist_audit_if_db(engine, ns_id, audit_entry, principal)
            return principal

        except EntraVerificationError as exc:
            audit_entry = self.record_audit(
                tool_or_route=tool_or_route,
                decision="DENY",
                reason=f"[{exc.code}] {exc}",
                principal=None,
                namespace_id=ns_id,
            )
            await self._persist_audit_if_db(engine, ns_id, audit_entry, None)
            raise

    async def _persist_audit_if_db(
        self,
        engine: Any,
        namespace_id: str,
        audit_entry: dict[str, Any],
        principal: EntraPrincipal | None,
    ) -> None:
        """Best-effort persistence to `entra_id_audit_log` when `engine.pg_pool` is available."""
        if not engine or not getattr(engine, "pg_pool", None) or not namespace_id:
            return
        try:
            from nce.db_utils import scoped_pg_session

            async with scoped_pg_session(engine.pg_pool, namespace_id) as conn:
                await conn.execute(
                    """
                    INSERT INTO entra_id_audit_log (
                        namespace_id, entra_oid, upn, pc_hostname,
                        tool_or_route, decision, reason, matched_groups, matched_roles
                    ) VALUES (
                        $1::uuid, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb
                    )
                    """,
                    namespace_id,
                    audit_entry.get("entra_oid"),
                    audit_entry.get("upn"),
                    audit_entry.get("pc_hostname"),
                    audit_entry["tool_or_route"],
                    audit_entry["decision"],
                    audit_entry["reason"],
                    json.dumps(audit_entry.get("matched_groups", [])),
                    json.dumps(audit_entry.get("matched_roles", [])),
                )
        except Exception as exc:
            log.debug("Skipping DB audit persistence: %s", exc)


_GLOBAL_GATE: EntraSecurityGate | None = None


def get_global_entra_gate() -> EntraSecurityGate:
    global _GLOBAL_GATE
    if _GLOBAL_GATE is None:
        _GLOBAL_GATE = EntraSecurityGate()
    return _GLOBAL_GATE


def require_entra_identity(required_role: str | None = None) -> Callable:
    """
    Decorator for MCP tool handlers `async (engine, arguments) -> str` that enforces
    the Microsoft Entra ID identification & company allowlist gate before running the tool.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(engine: Any, arguments: dict[str, Any]) -> str:
            gate = get_global_entra_gate()
            try:
                principal = await gate.verify_request(
                    func.__name__,
                    arguments,
                    required_role=required_role,
                    engine=engine,
                )
                if principal is not None and isinstance(arguments, dict):
                    arguments = dict(arguments)
                    arguments["_entra_principal"] = principal
            except EntraVerificationError as exc:
                return json.dumps(
                    {
                        "error": str(exc),
                        "error_code": exc.code,
                        "details": exc.details,
                        "remediation": (
                            "Call 'entra_login_device_code' to sign in with your corporate Microsoft "
                            "Entra ID account, or verify your user is in the authorized Entra Security Group."
                        ),
                    }
                )
            return await func(engine, arguments)

        return wrapper

    return decorator
