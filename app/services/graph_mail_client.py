"""Microsoft Graph API client for reading and sending emails.

Uses client-credentials flow (application permissions):
  - Mail.Read (read mailbox)
  - Mail.Send (send replies)

Requires Azure AD App Registration with admin-consented application permissions.
"""

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
_GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class GraphMailClient:
    def __init__(
        self,
        *,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        mailbox: str,
    ) -> None:
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._mailbox = mailbox
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    async def _ensure_token(self) -> str:
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        url = _TOKEN_URL.format(tenant_id=self._tenant_id)
        data = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, data=data)
            resp.raise_for_status()
            body = resp.json()

        self._access_token = body["access_token"]
        self._token_expires_at = time.time() + body.get("expires_in", 3600)
        return self._access_token

    async def _headers(self) -> dict[str, str]:
        token = await self._ensure_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def fetch_unread(self, *, top: int = 20) -> list[dict[str, Any]]:
        """Fetch unread emails from the support mailbox."""
        headers = await self._headers()
        url = (
            f"{_GRAPH_BASE}/users/{self._mailbox}/messages"
            f"?$filter=isRead eq false"
            f"&$top={top}"
            f"&$orderby=receivedDateTime desc"
            f"&$select=id,conversationId,subject,from,body,receivedDateTime,isRead"
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json().get("value", [])

    async def mark_read(self, message_id: str) -> None:
        """Mark a message as read."""
        headers = await self._headers()
        url = f"{_GRAPH_BASE}/users/{self._mailbox}/messages/{message_id}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.patch(
                url, headers=headers, json={"isRead": True}
            )
            resp.raise_for_status()

    async def send_reply(self, message_id: str, body_html: str) -> None:
        """Reply to a message."""
        headers = await self._headers()
        url = f"{_GRAPH_BASE}/users/{self._mailbox}/messages/{message_id}/reply"
        payload = {
            "message": {
                "body": {
                    "contentType": "HTML",
                    "content": body_html,
                }
            }
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()

    async def send_mail(
        self, *, to: str, subject: str, body_html: str
    ) -> None:
        """Send a new email (for manual replies from dashboard)."""
        headers = await self._headers()
        url = f"{_GRAPH_BASE}/users/{self._mailbox}/sendMail"
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "HTML", "content": body_html},
                "toRecipients": [{"emailAddress": {"address": to}}],
            },
            "saveToSentItems": True,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
