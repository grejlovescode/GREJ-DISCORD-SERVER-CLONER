"""
cloner.py — Core server cloning logic.

Source server: regular member access (View Channels only is fine).
Target server: must be owner or admin.

clone_options is a set of strings controlling what gets cloned:
  "server_settings" — name, icon, banner, splash, verification level, etc.
  "roles"           — all non-managed, non-@everyone roles
  "categories"      — channel categories
  "text_channels"   — text / announcement / forum channels
  "voice_channels"  — voice & stage channels
  "permissions"     — channel permission overwrites (applied per-channel)
  "emojis"          — custom emojis
  "stickers"        — custom stickers
  "messages"        — messages via webhooks (slow, opt-in)
"""

import asyncio
import os
from typing import Callable, Set

from api import DiscordAPI
from rich.console import Console

console = Console()

# Channel type constants
CH_TEXT        = 0
CH_VOICE       = 2
CH_CATEGORY    = 4
CH_ANNOUNCEMENT= 5
CH_STAGE       = 13
CH_FORUM       = 15
CH_MEDIA       = 16

# Sticker format → extension + mime
STICKER_FORMAT = {
    1: ("png",  "image/png"),
    2: ("apng", "image/apng"),
    3: ("json", "application/json"),   # Lottie — not uploadable, skipped
    4: ("gif",  "image/gif"),
}


class ServerCloner:
    def __init__(
        self,
        api: DiscordAPI,
        source_id: str,
        target_id: str,
        clone_options: Set[str] | None = None,
        clone_messages: bool = False,
        clear_options: Set[str] | None = None,
        message_limit: int = 50,
        on_progress: Callable[[str, int, int], None] | None = None,
    ):
        self.api = api
        self.source_id = source_id
        self.target_id = target_id
        self.clone_options: Set[str] = clone_options or {
            "server_settings", "roles", "categories",
            "text_channels", "voice_channels", "permissions",
            "emojis", "stickers",
        }
        self.clone_messages = clone_messages
        # clear_options controls what gets wiped from target before cloning.
        # None or empty set = skip clearing entirely.
        self.clear_options: Set[str] = clear_options if clear_options is not None else {
            "channels", "roles", "emojis", "stickers"
        }
        self.message_limit = message_limit
        self.on_progress = on_progress

        # Maps source IDs → newly created target IDs
        self._role_map: dict[str, str] = {}
        self._channel_map: dict[str, str] = {}

    def _has(self, option: str) -> bool:
        return option in self.clone_options

    def _progress(self, phase: str, current: int, total: int):
        if self.on_progress:
            self.on_progress(phase, current, total)

    # ── Public entry point ────────────────────────────────────────────────────

    async def run(self) -> None:
        console.print("\n[bold cyan]Fetching source server info...[/bold cyan]")
        source = await self.api.get_guild(self.source_id)
        console.print(
            f"  [green]Source:[/green] {source['name']} "
            f"([dim]{source.get('approximate_member_count', '?')} members[/dim])"
        )

        if self.clear_options:
            await self._clear_target()

        if self._has("server_settings"):
            await self._clone_server_settings(source)

        if self._has("roles"):
            await self._clone_roles()

        # Channels (categories first, then text/voice based on options)
        if self._has("categories") or self._has("text_channels") or self._has("voice_channels"):
            await self._clone_channels()

        if self._has("emojis"):
            await self._clone_emojis()

        if self._has("stickers"):
            await self._clone_stickers()

        if self.clone_messages:
            await self._clone_messages()

        console.print("\n[bold green]✓ Cloning complete![/bold green]")

    # ── Clear target ──────────────────────────────────────────────────────────

    async def _clear_target(self) -> None:
        what = self.clear_options
        console.print(
            f"\n[bold yellow]Clearing target server "
            f"({', '.join(sorted(what))})...[/bold yellow]"
        )

        if "channels" in what:
            channels = await self.api.get_channels(self.target_id)
            for ch in channels:
                try:
                    await self.api.delete_channel(ch["id"])
                    await asyncio.sleep(0.3)
                except Exception:
                    pass  # skip — no permission or already gone

        if "roles" in what:
            roles = await self.api.get_roles(self.target_id)
            everyone_role_id = self.target_id
            for role in roles:
                if role["id"] == everyone_role_id or role.get("managed"):
                    continue
                try:
                    await self.api.delete_role(self.target_id, role["id"])
                    await asyncio.sleep(0.3)
                except Exception:
                    pass  # skip — managed/higher role or no permission

        if "emojis" in what:
            emojis = await self.api.get_emojis(self.target_id)
            for emoji in emojis:
                try:
                    await self.api.delete_emoji(self.target_id, emoji["id"])
                    await asyncio.sleep(0.3)
                except Exception:
                    pass  # skip

        if "stickers" in what:
            try:
                stickers = await self.api.get_stickers(self.target_id)
                for sticker in stickers:
                    try:
                        await self.api.delete_sticker(self.target_id, sticker["id"])
                        await asyncio.sleep(0.3)
                    except Exception:
                        pass  # skip
            except Exception:
                pass

        cleared = ", ".join(sorted(what))
        console.print(f"  [green]Done — cleared: {cleared}[/green]")


    # ── Server settings ───────────────────────────────────────────────────────

    async def _clone_server_settings(self, source: dict) -> None:
        console.print("\n[bold cyan]Cloning server settings...[/bold cyan]")
        payload: dict = {"name": source["name"]}

        if source.get("icon"):
            try:
                ext = "gif" if source["icon"].startswith("a_") else "png"
                icon_url = f"https://cdn.discordapp.com/icons/{self.source_id}/{source['icon']}.{ext}?size=1024"
                payload["icon"] = await self.api.download_asset(icon_url)
                console.print("  [green]✓[/green] Icon")
            except Exception as e:
                console.print(f"  [yellow]Could not clone icon: {e}[/yellow]")

        if source.get("banner"):
            try:
                banner_url = f"https://cdn.discordapp.com/banners/{self.source_id}/{source['banner']}.png?size=1024"
                payload["banner"] = await self.api.download_asset(banner_url)
                console.print("  [green]✓[/green] Banner")
            except Exception as e:
                console.print(f"  [yellow]Could not clone banner: {e}[/yellow]")

        if source.get("splash"):
            try:
                splash_url = f"https://cdn.discordapp.com/splashes/{self.source_id}/{source['splash']}.png?size=1024"
                payload["splash"] = await self.api.download_asset(splash_url)
                console.print("  [green]✓[/green] Invite splash")
            except Exception as e:
                console.print(f"  [yellow]Could not clone splash: {e}[/yellow]")

        for key in ("verification_level", "default_message_notifications",
                    "explicit_content_filter", "afk_timeout"):
            if key in source:
                payload[key] = source[key]

        try:
            await self.api.modify_guild(self.target_id, payload)
            console.print("  [green]✓[/green] Server settings applied.")
        except Exception as e:
            console.print(f"  [red]Could not apply server settings: {e}[/red]")

    # ── Roles ─────────────────────────────────────────────────────────────────

    async def _clone_roles(self) -> None:
        roles = await self.api.get_roles(self.source_id)
        clonable = [
            r for r in roles
            if not r.get("managed") and r["name"] != "@everyone"
        ]
        clonable.sort(key=lambda r: r["position"], reverse=True)

        console.print(f"\n[bold cyan]Cloning {len(clonable)} roles...[/bold cyan]")
        for i, role in enumerate(clonable, 1):
            payload = {
                "name": role["name"],
                "permissions": role["permissions"],
                "color": role["color"],
                "hoist": role["hoist"],
                "mentionable": role["mentionable"],
            }
            try:
                new_role = await self.api.create_role(self.target_id, payload)
                self._role_map[role["id"]] = new_role["id"]
                console.print(
                    f"  [{i}/{len(clonable)}] [green]✓[/green] @{role['name']}"
                )
            except Exception as e:
                console.print(
                    f"  [{i}/{len(clonable)}] [red]✗[/red] @{role['name']}: {e}"
                )
            self._progress("roles", i, len(clonable))
            await asyncio.sleep(0.4)

    # ── Channels ──────────────────────────────────────────────────────────────

    async def _clone_channels(self) -> None:
        channels = await self.api.get_channels(self.source_id)

        categories = sorted(
            [c for c in channels if c["type"] == CH_CATEGORY],
            key=lambda c: c.get("position", 0),
        )
        other = sorted(
            [c for c in channels if c["type"] != CH_CATEGORY],
            key=lambda c: c.get("position", 0),
        )

        # Filter based on options
        if not self._has("categories"):
            categories = []
        if not self._has("text_channels"):
            other = [c for c in other if c["type"] not in
                     (CH_TEXT, CH_ANNOUNCEMENT, CH_FORUM, CH_MEDIA)]
        if not self._has("voice_channels"):
            other = [c for c in other if c["type"] not in (CH_VOICE, CH_STAGE)]

        total = len(categories) + len(other)
        if total == 0:
            return

        console.print(f"\n[bold cyan]Cloning {total} channels...[/bold cyan]")
        idx = 0

        # 1. Categories first
        for cat in categories:
            idx += 1
            try:
                payload = self._build_channel_payload(cat, parent_id=None)
                new_cat = await self.api.create_channel(self.target_id, payload)
                self._channel_map[cat["id"]] = new_cat["id"]
                console.print(
                    f"  [{idx}/{total}] [green]✓[/green] 📁 {cat['name']}"
                )
            except Exception as e:
                console.print(
                    f"  [{idx}/{total}] [red]✗[/red] 📁 {cat['name']}: {e}"
                )
            self._progress("channels", idx, total)
            await asyncio.sleep(0.4)

        # 2. Channels (inside and outside categories)
        for ch in other:
            idx += 1
            parent_id = None
            if ch.get("parent_id") and ch["parent_id"] in self._channel_map:
                parent_id = self._channel_map[ch["parent_id"]]
            try:
                payload = self._build_channel_payload(ch, parent_id=parent_id)
                new_ch = await self.api.create_channel(self.target_id, payload)
                self._channel_map[ch["id"]] = new_ch["id"]
                icon = "🔊" if ch["type"] in (CH_VOICE, CH_STAGE) else "#"
                console.print(
                    f"  [{idx}/{total}] [green]✓[/green] {icon} {ch['name']}"
                )
            except Exception as e:
                console.print(
                    f"  [{idx}/{total}] [red]✗[/red] #{ch['name']}: {e}"
                )
            self._progress("channels", idx, total)
            await asyncio.sleep(0.4)

    def _build_channel_payload(
        self, channel: dict, parent_id: str | None
    ) -> dict:
        payload: dict = {
            "name": channel["name"],
            "type": channel["type"],
            "position": channel.get("position", 0),
        }
        if parent_id:
            payload["parent_id"] = parent_id

        if channel["type"] in (CH_TEXT, CH_ANNOUNCEMENT):
            if channel.get("topic"):
                payload["topic"] = channel["topic"]
            payload["nsfw"] = channel.get("nsfw", False)
            payload["rate_limit_per_user"] = channel.get("rate_limit_per_user", 0)

        if channel["type"] in (CH_VOICE, CH_STAGE):
            payload["bitrate"] = channel.get("bitrate", 64000)
            payload["user_limit"] = channel.get("user_limit", 0)

        # Permission overwrites — only if "permissions" option is selected
        if self._has("permissions"):
            overwrites = channel.get("permission_overwrites", [])
            remapped = []
            for ow in overwrites:
                new_id = self._role_map.get(ow["id"], ow["id"])
                remapped.append({
                    "id": new_id,
                    "type": ow["type"],
                    "allow": ow["allow"],
                    "deny": ow["deny"],
                })
            if remapped:
                payload["permission_overwrites"] = remapped

        return payload

    # ── Emojis ────────────────────────────────────────────────────────────────

    async def _clone_emojis(self) -> None:
        emojis = await self.api.get_emojis(self.source_id)
        if not emojis:
            console.print("\n[dim]No emojis to clone.[/dim]")
            return

        console.print(f"\n[bold cyan]Cloning {len(emojis)} emojis...[/bold cyan]")
        for i, emoji in enumerate(emojis, 1):
            ext = "gif" if emoji.get("animated") else "png"
            url = f"https://cdn.discordapp.com/emojis/{emoji['id']}.{ext}"
            try:
                image_data = await self.api.download_asset(url)
                await self.api.create_emoji(
                    self.target_id, {"name": emoji["name"], "image": image_data}
                )
                tag = "GIF" if emoji.get("animated") else "PNG"
                console.print(
                    f"  [{i}/{len(emojis)}] [green]✓[/green] :{emoji['name']}: [{tag}]"
                )
            except Exception as e:
                console.print(
                    f"  [{i}/{len(emojis)}] [red]✗[/red] :{emoji['name']}: {e}"
                )
            self._progress("emojis", i, len(emojis))
            await asyncio.sleep(0.5)

    # ── Stickers ──────────────────────────────────────────────────────────────

    async def _clone_stickers(self) -> None:
        try:
            stickers = await self.api.get_stickers(self.source_id)
        except Exception as e:
            console.print(f"\n[yellow]Could not fetch stickers: {e}[/yellow]")
            return

        # Only guild stickers (type 2), skip standard/Nitro packs (type 1)
        guild_stickers = [s for s in stickers if s.get("type") == 2]
        if not guild_stickers:
            console.print("\n[dim]No custom stickers to clone.[/dim]")
            return

        console.print(
            f"\n[bold cyan]Cloning {len(guild_stickers)} stickers...[/bold cyan]"
        )
        for i, sticker in enumerate(guild_stickers, 1):
            fmt = sticker.get("format_type", 1)
            if fmt == 3:
                # Lottie JSON — Discord does not accept re-upload
                console.print(
                    f"  [{i}/{len(guild_stickers)}] [yellow]⊘[/yellow] "
                    f"{sticker['name']} (Lottie — cannot re-upload)"
                )
                continue

            ext, mime = STICKER_FORMAT.get(fmt, ("png", "image/png"))
            url = f"https://cdn.discordapp.com/stickers/{sticker['id']}.{ext}"
            try:
                raw, detected_mime = await self.api.download_bytes(url)
                await self.api.create_sticker(
                    guild_id=self.target_id,
                    name=sticker["name"],
                    description=sticker.get("description", ""),
                    tags=sticker.get("tags", sticker["name"]),
                    file_bytes=raw,
                    filename=f"{sticker['name']}.{ext}",
                    mime_type=detected_mime or mime,
                )
                console.print(
                    f"  [{i}/{len(guild_stickers)}] [green]✓[/green] "
                    f"{sticker['name']} [{ext.upper()}]"
                )
            except Exception as e:
                console.print(
                    f"  [{i}/{len(guild_stickers)}] [red]✗[/red] "
                    f"{sticker['name']}: {e}"
                )
            self._progress("stickers", i, len(guild_stickers))
            await asyncio.sleep(0.6)

    # ── Messages ──────────────────────────────────────────────────────────────

    async def _clone_messages(self) -> None:
        source_channels = await self.api.get_channels(self.source_id)
        text_channels = [c for c in source_channels if c["type"] == CH_TEXT]

        console.print(
            f"\n[bold cyan]Cloning messages from {len(text_channels)} text channels...[/bold cyan]"
        )

        for ch in text_channels:
            src_id = ch["id"]
            if src_id not in self._channel_map:
                continue
            tgt_id = self._channel_map[src_id]

            try:
                wh = await self.api.create_webhook(tgt_id, "Cloner")
            except Exception as e:
                console.print(
                    f"  [red]Could not create webhook in #{ch['name']}: {e}[/red]"
                )
                continue

            messages = await self._fetch_all_messages(src_id)
            console.print(
                f"  [cyan]#{ch['name']}[/cyan] — {len(messages)} messages"
            )

            for msg in messages:
                content = msg.get("content", "")
                embeds = msg.get("embeds", [])
                author = msg.get("author", {})
                username = author.get("username", "Unknown")
                avatar = author.get("avatar")
                uid = author.get("id", "")

                avatar_url: str | None = None
                if avatar:
                    ext = "gif" if avatar.startswith("a_") else "png"
                    avatar_url = f"https://cdn.discordapp.com/avatars/{uid}/{avatar}.{ext}"

                payload: dict = {"username": username}
                if avatar_url:
                    payload["avatar_url"] = avatar_url
                if content:
                    payload["content"] = content[:2000]
                if embeds:
                    payload["embeds"] = embeds[:10]

                if not content and not embeds:
                    continue

                try:
                    await self.api.execute_webhook(wh["id"], wh["token"], payload)
                    await asyncio.sleep(0.8)
                except Exception as e:
                    console.print(f"    [red]Webhook error: {e}[/red]")

    async def _fetch_all_messages(self, channel_id: str) -> list[dict]:
        all_msgs: list[dict] = []
        before: str | None = None
        remaining = self.message_limit

        while remaining > 0:
            batch_size = min(100, remaining)
            batch = await self.api.get_messages(
                channel_id, limit=batch_size, before=before
            )
            if not batch:
                break
            all_msgs.extend(batch)
            remaining -= len(batch)
            if len(batch) < batch_size:
                break
            before = batch[-1]["id"]
            await asyncio.sleep(0.5)

        all_msgs.reverse()
        return all_msgs
