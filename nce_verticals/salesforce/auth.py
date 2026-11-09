"""
nce_verticals/salesforce/auth.py
================================
Salesforce Multi-Flow Token Manager supporting all 3 authentication modes:
1. `client_credentials` / `refresh_token`: Connected App OAuth 2.0 flows.
2. `jwt_bearer`: OAuth 2.0 JWT Bearer flow (`urn:ietf:params:oauth:grant-type:jwt-bearer`).
3. `entra_delegated`: Pass-through / OBO token exchange via the Entra ID Identification Point.

Works standalone (in-memory token cache) and with Redis (`nce:sf:token:{instance}`).
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any

from nce_verticals.entra_id._http_compat import httpx

log = logging.getLogger("nce_verticals.salesforce.auth")

HTTP_TIMEOUT = httpx.Timeout(connect=4.0, read=5.0, write=4.0, pool=4.0)


@dataclasses.dataclass(slots=True)
class SalesforceAuthConfig:
    """Configuration for the Standalone Salesforce Vertical Engine."""

    enabled: bool = True
    instance_url: str = ""
    login_url: str = "https://login.salesforce.com"
    api_version: str = "v60.0"
    auth_mode: str = "client_credentials"  # 'client_credentials' | 'refresh_token' | 'jwt_bearer' | 'entra_delegated'
    client_id: str = ""
    client_secret: str = ""
    refresh_token: str = ""
    jwt_subject: str = ""
    jwt_private_key: str = ""
    static_access_token: str = ""
    webhook_secret: str = ""
    standalone_passthrough: bool = True
    sync_enabled: bool = True
    require_entra_gate: bool = True
    sync_objects: list[str] = dataclasses.field(
        default_factory=lambda: [
            "Account",
            "Contact",
            "Lead",
            "Opportunity",
            "Case",
            "Task",
        ]
    )

    @classmethod
    def from_env(cls) -> SalesforceAuthConfig:
        sync_objs_raw = os.environ.get(
            "NCE_SF_SYNC_OBJECTS",
            "Account,Contact,Lead,Opportunity,Case,Task",
        )
        return cls(
            enabled=os.environ.get("NCE_SF_ENABLED", "true").lower()
            in ("1", "true", "yes"),
            instance_url=os.environ.get("NCE_SF_INSTANCE_URL", "").strip().rstrip("/"),
            login_url=os.environ.get("NCE_SF_LOGIN_URL", "https://login.salesforce.com")
            .strip()
            .rstrip("/"),
            api_version=os.environ.get("NCE_SF_API_VERSION", "v60.0").strip(),
            auth_mode=os.environ.get("NCE_SF_AUTH_MODE", "client_credentials")
            .strip()
            .lower(),
            client_id=os.environ.get("NCE_SF_CLIENT_ID", "").strip(),
            client_secret=os.environ.get("NCE_SF_CLIENT_SECRET", "").strip(),
            refresh_token=os.environ.get("NCE_SF_REFRESH_TOKEN", "").strip(),
            jwt_subject=os.environ.get("NCE_SF_JWT_SUBJECT", "").strip(),
            jwt_private_key=os.environ.get("NCE_SF_JWT_PRIVATE_KEY", "").strip(),
            static_access_token=os.environ.get("NCE_SF_ACCESS_TOKEN", "").strip(),
            webhook_secret=os.environ.get("NCE_SF_WEBHOOK_SECRET", "").strip(),
            standalone_passthrough=os.environ.get(
                "NCE_SF_STANDALONE_PASSTHROUGH", "true"
            ).lower()
            in ("1", "true", "yes"),
            sync_enabled=os.environ.get("NCE_SF_SYNC_ENABLED", "true").lower()
            in ("1", "true", "yes"),
            require_entra_gate=os.environ.get(
                "NCE_SF_REQUIRE_ENTRA_GATE", "true"
            ).lower()
            in ("1", "true", "yes"),
            sync_objects=[s.strip() for s in sync_objs_raw.split(",") if s.strip()],
        )

    def to_safe_dict(self) -> dict[str, Any]:
        """Return safe dictionary with secrets masked."""
        return {
            "enabled": self.enabled,
            "instance_url": self.instance_url,
            "login_url": self.login_url,
            "api_version": self.api_version,
            "auth_mode": self.auth_mode,
            "client_id": self.client_id,
            "client_secret_set": bool(self.client_secret),
            "refresh_token_set": bool(self.refresh_token),
            "jwt_subject": self.jwt_subject,
            "jwt_private_key_set": bool(self.jwt_private_key),
            "static_access_token_set": bool(self.static_access_token),
            "webhook_secret_set": bool(self.webhook_secret),
            "standalone_passthrough": self.standalone_passthrough,
            "sync_enabled": self.sync_enabled,
            "require_entra_gate": self.require_entra_gate,
            "sync_objects": list(self.sync_objects),
        }


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def build_salesforce_jwt_assertion(
    *,
    client_id: str,
    subject: str,
    audience: str,
    private_key_pem: str,
    lifetime_seconds: int = 180,
) -> str:
    """
    Build a signed OAuth 2.0 JWT Bearer assertion for Salesforce (`RS256` if `cryptography`
    is installed with an RSA PEM key, or `HS256` fallback for test keys).
    """
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": client_id,
        "sub": subject,
        "aud": audience,
        "exp": now + lifetime_seconds,
        "iat": now,
    }
    signing_input = (
        f"{_b64url(json.dumps(header, separators=(',', ':')).encode('utf-8'))}."
        f"{_b64url(json.dumps(claims, separators=(',', ':')).encode('utf-8'))}"
    ).encode("ascii")

    if "BEGIN" in private_key_pem:
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding

            key = serialization.load_pem_private_key(
                private_key_pem.encode("utf-8"), password=None
            )
            sig = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())  # type: ignore[union-attr]
            return f"{signing_input.decode('ascii')}.{_b64url(sig)}"
        except Exception as exc:
            log.warning(
                "RSA signing failed (%s); falling back to HMAC-SHA256 assertion signature",
                exc,
            )

    sig_hmac = hmac.new(
        private_key_pem.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    return f"{signing_input.decode('ascii')}.{_b64url(sig_hmac)}"


class SalesforceTokenManager:
    """Manages Salesforce OAuth 2.0 tokens across all 3 supported flows."""

    def __init__(
        self,
        config: SalesforceAuthConfig | None = None,
        redis_client: Any = None,
    ) -> None:
        self.config = config or SalesforceAuthConfig.from_env()
        self._redis = redis_client
        self._cached_token: str | None = None
        self._cached_instance_url: str | None = None
        self._expires_at: float = 0.0

    def invalidate(self) -> None:
        self._cached_token = None
        self._expires_at = 0.0

    async def get_access_token(
        self,
        *,
        entra_token: str | None = None,
        force_refresh: bool = False,
    ) -> tuple[str, str]:
        """
        Return `(access_token, instance_url)`.
        Supports:
        - `client_credentials`
        - `refresh_token`
        - `jwt_bearer`
        - `entra_delegated`
        """
        now = time.time()
        if (
            not force_refresh
            and self._cached_token
            and now < self._expires_at
            and self.config.auth_mode != "entra_delegated"
        ):
            return self._cached_token, (
                self._cached_instance_url or self.config.instance_url
            )

        if self.config.static_access_token and not force_refresh:
            return self.config.static_access_token, self.config.instance_url

        mode = self.config.auth_mode
        token_endpoint = (
            f"{self.config.login_url or self.config.instance_url}/services/oauth2/token"
        )

        if mode == "entra_delegated":
            if entra_token:
                # Exchange or pass-through the caller's verified Entra ID token
                if not self.config.client_id:
                    return entra_token, self.config.instance_url
                form_data = {
                    "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                    "subject_token": entra_token,
                    "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
                    "client_id": self.config.client_id,
                }
                if self.config.client_secret:
                    form_data["client_secret"] = self.config.client_secret
            else:
                raise RuntimeError(
                    "Salesforce auth_mode='entra_delegated' requires a verified Entra ID token."
                )

        elif mode == "jwt_bearer":
            if not (
                self.config.client_id
                and self.config.jwt_subject
                and self.config.jwt_private_key
            ):
                raise RuntimeError(
                    "Salesforce jwt_bearer mode requires client_id, jwt_subject, and jwt_private_key."
                )
            assertion = build_salesforce_jwt_assertion(
                client_id=self.config.client_id,
                subject=self.config.jwt_subject,
                audience=self.config.login_url or "https://login.salesforce.com",
                private_key_pem=self.config.jwt_private_key,
            )
            form_data = {
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            }

        elif mode == "refresh_token":
            if not (self.config.client_id and self.config.refresh_token):
                raise RuntimeError(
                    "Salesforce refresh_token mode requires client_id and refresh_token."
                )
            form_data = {
                "grant_type": "refresh_token",
                "client_id": self.config.client_id,
                "refresh_token": self.config.refresh_token,
            }
            if self.config.client_secret:
                form_data["client_secret"] = self.config.client_secret

        else:
            # Default: client_credentials
            if not (self.config.client_id and self.config.client_secret):
                raise RuntimeError(
                    "Salesforce client_credentials mode requires client_id and client_secret."
                )
            form_data = {
                "grant_type": "client_credentials",
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
            }

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.post(token_endpoint, data=form_data)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Salesforce OAuth2 token acquisition failed ({mode}, HTTP {resp.status_code})"
                )
            data = resp.json()

        access_token = str(data.get("access_token") or "")
        instance_url = str(data.get("instance_url") or self.config.instance_url).rstrip(
            "/"
        )
        if not access_token:
            raise RuntimeError("Salesforce token response did not include access_token")

        self._cached_token = access_token
        self._cached_instance_url = instance_url
        self._expires_at = now + 3300.0
        return access_token, instance_url
