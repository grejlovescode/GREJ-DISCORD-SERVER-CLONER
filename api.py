"""
api.py — Discord REST API wrapper for the selfbot cloner.
Handles rate limiting, retries, and all endpoints needed for cloning.
"""

import asyncio
import base64
import mimetypes
from typing import Any

import httpx

BASE_URL = "https://discord.com/api/v10"


class DiscordAPI:
    """Async Discord REST client using a user token (selfbot)."""

    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": token,
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        }
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(headers=self.headers, timeout=30)
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        """Make an HTTP request with automatic rate-limit retry."""
        url = f"{BASE_URL}{path}"
        for attempt in range(10):
            resp = await self._client.request(method, url, **kwargs)
            if resp.status_code == 429:
                data = resp.json()
                retry_after = float(data.get("retry_after", 1.0))
                await asyncio.sleep(retry_after)
                continue
            if resp.status_code == 204:
                return None
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Discord API error {resp.status_code} on {method} {path}: {resp.text}"
                )
            return resp.json()
        raise RuntimeError(f"Rate limited too many times on {method} {path}")

    async def get(self, path: str, **kwargs) -> Any:
        return await self._request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs) -> Any:
        return await self._request("POST", path, **kwargs)

    async def patch(self, path: str, **kwargs) -> Any:
        return await self._request("PATCH", path, **kwargs)

    async def put(self, path: str, **kwargs) -> Any:
        return await self._request("PUT", path, **kwargs)

    async def delete(self, path: str, **kwargs) -> Any:
        return await self._request("DELETE", path, **kwargs)

    # ── Guild ────────────────────────────────────────────────────────────────

    async def get_guild(self, guild_id: str) -> dict:
        return await self.get(f"/guilds/{guild_id}?with_counts=true")

    async def modify_guild(self, guild_id: str, payload: dict) -> dict:
        return await self.patch(f"/guilds/{guild_id}", json=payload)

    # ── Roles ────────────────────────────────────────────────────────────────

    async def get_roles(self, guild_id: str) -> list[dict]:
        return await self.get(f"/guilds/{guild_id}/roles")

    async def create_role(self, guild_id: str, payload: dict) -> dict:
        return await self.post(f"/guilds/{guild_id}/roles", json=payload)

    async def delete_role(self, guild_id: str, role_id: str) -> None:
        await self.delete(f"/guilds/{guild_id}/roles/{role_id}")

    # ── Channels ─────────────────────────────────────────────────────────────

    async def get_channels(self, guild_id: str) -> list[dict]:
        return await self.get(f"/guilds/{guild_id}/channels")

    async def create_channel(self, guild_id: str, payload: dict) -> dict:
        return await self.post(f"/guilds/{guild_id}/channels", json=payload)

    async def delete_channel(self, channel_id: str) -> None:
        await self.delete(f"/channels/{channel_id}")

    # ── Messages ─────────────────────────────────────────────────────────────

    async def get_messages(
        self, channel_id: str, limit: int = 100, before: str | None = None
    ) -> list[dict]:
        params: dict = {"limit": limit}
        if before:
            params["before"] = before
        return await self.get(f"/channels/{channel_id}/messages", params=params)

    # ── Webhooks ─────────────────────────────────────────────────────────────

    async def create_webhook(self, channel_id: str, name: str) -> dict:
        return await self.post(
            f"/channels/{channel_id}/webhooks", json={"name": name}
        )

    async def execute_webhook(
        self, webhook_id: str, webhook_token: str, payload: dict
    ) -> None:
        url = f"https://discord.com/api/webhooks/{webhook_id}/{webhook_token}"
        resp = await self._client.post(url, json=payload)
        if resp.status_code == 429:
            retry_after = resp.json().get("retry_after", 1.0)
            await asyncio.sleep(float(retry_after))

    # ── Emojis ───────────────────────────────────────────────────────────────

    async def get_emojis(self, guild_id: str) -> list[dict]:
        return await self.get(f"/guilds/{guild_id}/emojis")

    async def create_emoji(self, guild_id: str, payload: dict) -> dict:
        return await self.post(f"/guilds/{guild_id}/emojis", json=payload)

    async def delete_emoji(self, guild_id: str, emoji_id: str) -> None:
        await self.delete(f"/guilds/{guild_id}/emojis/{emoji_id}")

    # ── Stickers ─────────────────────────────────────────────────────────────

    async def get_stickers(self, guild_id: str) -> list[dict]:
        return await self.get(f"/guilds/{guild_id}/stickers")

    async def create_sticker(
        self,
        guild_id: str,
        name: str,
        description: str,
        tags: str,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
    ) -> dict:
        """Create a guild sticker using multipart form upload."""
        # Must send multipart, not JSON
        files = {"file": (filename, file_bytes, mime_type)}
        data = {"name": name, "description": description or ".", "tags": tags}
        # Temporarily remove Content-Type so httpx sets multipart boundary
        headers = {k: v for k, v in self.headers.items() if k != "Content-Type"}
        url = f"{BASE_URL}/guilds/{guild_id}/stickers"
        for _ in range(10):
            resp = await self._client.post(url, headers=headers, data=data, files=files)
            if resp.status_code == 429:
                retry_after = float(resp.json().get("retry_after", 1.0))
                await asyncio.sleep(retry_after)
                continue
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Discord API error {resp.status_code} on POST sticker: {resp.text}"
                )
            return resp.json()
        raise RuntimeError("Rate limited too many times creating sticker")

    async def delete_sticker(self, guild_id: str, sticker_id: str) -> None:
        await self.delete(f"/guilds/{guild_id}/stickers/{sticker_id}")

    # ── CDN helpers ──────────────────────────────────────────────────────────

    async def download_asset(self, url: str) -> str:
        """Download a CDN asset and return as a base64 data URI."""
        resp = await self._client.get(url)
        resp.raise_for_status()
        mime = mimetypes.guess_type(url.split("?")[0])[0] or "image/png"
        b64 = base64.b64encode(resp.content).decode()
        return f"data:{mime};base64,{b64}"

    async def download_bytes(self, url: str) -> tuple[bytes, str]:
        """Download a CDN asset and return raw bytes + mime type."""
        resp = await self._client.get(url)
        resp.raise_for_status()
        mime = mimetypes.guess_type(url.split("?")[0])[0] or "image/png"
        return resp.content, mime

    async def get_current_user(self) -> dict:
        return await self.get("/users/@me")
