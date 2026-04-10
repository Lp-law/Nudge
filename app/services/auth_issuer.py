from dataclasses import dataclass

from app.core.config import get_settings
from app.core.security import (
    build_token_claims,
    get_token_state_store,
    issue_signed_token,
    verify_token_string,
)


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    refresh_expires_in: int
    tier: str = "personal"


class AuthIssuerService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _signing_key(self) -> str:
        key = (self.settings.nudge_token_signing_key or "").strip()
        if not key:
            raise ValueError("Missing token signing key.")
        return key

    async def issue_token_pair(self, *, subject: str, device_id: str, tier: str = "personal") -> TokenPair:
        signing_key = self._signing_key()
        access_claims = build_token_claims(
            subject=subject,
            issuer=self.settings.nudge_token_issuer,
            audience=self.settings.nudge_token_audience,
            scope=self.settings.nudge_required_scope,
            token_type="access",
            ttl_seconds=self.settings.nudge_access_token_ttl_seconds,
            device_id=device_id,
            tier=tier,
        )
        refresh_claims = build_token_claims(
            subject=subject,
            issuer=self.settings.nudge_token_issuer,
            audience=self.settings.nudge_token_audience,
            scope="",
            token_type="refresh",
            ttl_seconds=self.settings.nudge_refresh_token_ttl_seconds,
            device_id=device_id,
            tier=tier,
        )
        access_token = issue_signed_token(access_claims, signing_key)
        refresh_token = issue_signed_token(refresh_claims, signing_key)
        await get_token_state_store(self.settings).store_refresh_jti(
            str(refresh_claims["jti"]),
            int(refresh_claims["exp"]),
            subject=subject,
            device_id=device_id,
        )
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_in=int(self.settings.nudge_access_token_ttl_seconds),
            refresh_expires_in=int(self.settings.nudge_refresh_token_ttl_seconds),
            tier=tier or "personal",
        )

    async def refresh(self, refresh_token: str) -> TokenPair:
        context = await verify_token_string(
            refresh_token,
            self.settings,
            expected_token_type="refresh",
            require_scope=False,
        )
        if context is None:
            raise ValueError("Invalid refresh token.")

        consumed = await get_token_state_store(self.settings).consume_refresh_jti(context.jti)
        if not consumed:
            raise ValueError("Refresh token is no longer active.")

        # Note: consume_refresh_jti now atomically revokes the JTI, so a
        # separate revoke_jti call is no longer needed.
        return await self.issue_token_pair(
            subject=context.principal,
            device_id=context.device_id,
            tier=context.tier,
        )

    async def revoke(self, token: str) -> None:
        access_context = await verify_token_string(
            token,
            self.settings,
            expected_token_type="access",
            require_scope=False,
        )
        if access_context is not None and access_context.jti:
            await get_token_state_store(self.settings).revoke_jti(
                access_context.jti,
                access_context.expires_at,
            )
            return

        refresh_context = await verify_token_string(
            token,
            self.settings,
            expected_token_type="refresh",
            require_scope=False,
        )
        if refresh_context is None or not refresh_context.jti:
            raise ValueError("Invalid token.")
        await get_token_state_store(self.settings).revoke_jti(
            refresh_context.jti,
            refresh_context.expires_at,
        )
