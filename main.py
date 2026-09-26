"""
main.py — Discord Server Cloner (Selfbot)
Rich terminal UI with questionary prompts and live progress.
"""

import asyncio
import json
import os
import sys

import questionary
from rich import box
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.rule import Rule
from rich.text import Text
from rich.theme import Theme

from api import DiscordAPI
from cloner import ServerCloner

# ── Theme ────────────────────────────────────────────────────────────────────

THEME = Theme(
    {
        "primary": "bold #7289DA",
        "success": "bold #43B581",
        "warning": "bold #FAA61A",
        "error": "bold #F04747",
        "muted": "dim white",
        "label": "bold white",
    }
)

console = Console(theme=THEME)

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

BANNER = r"""
   ██████╗ ██████╗ ███████╗██╗     ██████╗ ██╗      ██████╗ ███╗   ██╗███████╗██████╗ 
  ██╔════╝ ██╔══██╗██╔════╝██║    ██╔════╝ ██║     ██╔═══██╗████╗  ██║██╔════╝██╔══██╗
  ██║  ███╗██████╔╝█████╗  ██║    ██║      ██║     ██║   ██║██╔██╗ ██║█████╗  ██████╔╝
  ██║   ██║██╔══██╗██╔══╝  ██║    ██║      ██║     ██║   ██║██║╚██╗██║██╔══╝  ██╔══██╗
  ╚██████╔╝██║  ██║███████╗██║    ╚██████╗ ███████╗╚██████╔╝██║ ╚████║███████╗██║  ██║
   ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝     ╚═════╝ ╚══════╝ ╚═════╝ ╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝
"""


# ── Config helpers ────────────────────────────────────────────────────────────

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}


def save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


# ── Questionary style ─────────────────────────────────────────────────────────

QSTYLE = questionary.Style(
    [
        ("qmark", "fg:#7289DA bold"),
        ("question", "fg:#ffffff bold"),
        ("answer", "fg:#43B581 bold"),
        ("pointer", "fg:#7289DA bold"),
        ("highlighted", "fg:#7289DA bold"),
        ("selected", "fg:#43B581"),
        ("separator", "fg:#6c6c6c"),
        ("instruction", "fg:#858585 italic"),
    ]
)


# ── Token validation ──────────────────────────────────────────────────────────

async def validate_token(token: str) -> dict | None:
    try:
        async with DiscordAPI(token) as api:
            user = await api.get_current_user()
            return user
    except Exception:
        return None


# ── Main UI ───────────────────────────────────────────────────────────────────

async def main() -> None:
    os.system("cls" if os.name == "nt" else "clear")

    # Banner
    console.print(
        Panel(
            Align.center(
                Text(BANNER, style="primary"),
            ),
            subtitle="[muted]GREJ Server Cloner — Selfbot Edition[/muted]",
            border_style="#7289DA",
            box=box.DOUBLE_EDGE,
            padding=(0, 2),
        )
    )

    console.print(
        Align.center(
            "[warning]⚠  Selfbots violate Discord ToS. Use responsibly.[/warning]"
        )
    )
    console.print()

    cfg = load_config()

    # ── Token ────────────────────────────────────────────────────────────────
    console.print(Rule("[primary]Step 1 — Authentication[/primary]"))

    saved_token = cfg.get("token", "")
    if saved_token:
        use_saved = await questionary.confirm(
            f"Use saved token? (ends in ...{saved_token[-6:]})",
            default=True,
            style=QSTYLE,
        ).ask_async()
        token = saved_token if use_saved else None
    else:
        token = None

    if not token:
        token = await questionary.password(
            "Enter your Discord user token:",
            style=QSTYLE,
        ).ask_async()

    console.print("  Validating token...", end=" ")
    user = await validate_token(token)
    if not user:
        console.print("[error]✗ Invalid token or network error.[/error]")
        sys.exit(1)

    console.print(
        f"[success]✓[/success] Logged in as [label]{user['username']}#{user.get('discriminator','0')}[/label]"
    )

    cfg["token"] = token
    save_config(cfg)

    # ── Server IDs ───────────────────────────────────────────────────────────
    console.print()
    console.print(Rule("[primary]Step 2 — Servers[/primary]"))
    console.print(
        "  [muted]Tip: Right-click a server → Copy Server ID (Developer Mode must be ON)[/muted]"
    )
    console.print()

    source_id = await questionary.text(
        "Source server ID (the server you want to clone FROM):",
        default=cfg.get("last_source", ""),
        style=QSTYLE,
    ).ask_async()

    target_id = await questionary.text(
        "Target server ID (the server you own, to clone INTO):",
        default=cfg.get("last_target", ""),
        style=QSTYLE,
    ).ask_async()

    cfg["last_source"] = source_id
    cfg["last_target"] = target_id
    save_config(cfg)

    # ── What to clone ────────────────────────────────────────────────────────
    console.print()
    console.print(Rule("[primary]Step 3 — What to clone[/primary]"))
    console.print(
        "  [muted]Space to toggle • Enter to confirm • Check \u26a1 Select All to enable everything[/muted]"
    )
    console.print()

    ALL_CLONE = {
        "server_settings", "roles", "categories",
        "text_channels", "voice_channels", "permissions",
        "emojis", "stickers",
    }

    clone_choices = await questionary.checkbox(
        "Select what to clone:",
        choices=[
            questionary.Choice("⚡  Select All",                                                value="select_all",     checked=False),
            questionary.Choice("─" * 45,                                                        value="__sep1__",        disabled=True),
            questionary.Choice("🏠  Server settings  (name, icon, banner, splash)",        value="server_settings", checked=True),
            questionary.Choice("👑  Roles             (colors, permissions, hoist)",        value="roles",           checked=True),
            questionary.Choice("📁  Categories",                                            value="categories",     checked=True),
            questionary.Choice("💬  Text channels     (topic, slowmode, NSFW)",             value="text_channels",  checked=True),
            questionary.Choice("🔊  Voice channels    (bitrate, user limit)",               value="voice_channels", checked=True),
            questionary.Choice("🔒  Permissions       (channel permission overwrites)",     value="permissions",    checked=True),
            questionary.Choice("😄  Emojis            (static + animated)",                 value="emojis",         checked=True),
            questionary.Choice("🎨  Stickers          (PNG/APNG/GIF, no Lottie)",          value="stickers",       checked=True),
            questionary.Choice("📝  Messages          (via webhooks — slow)",               value="messages",       checked=False),
        ],
        style=QSTYLE,
    ).ask_async()

    # If "Select All" was ticked, expand to every option including messages
    if "select_all" in clone_choices:
        clone_options = ALL_CLONE.copy()
        clone_messages = True
    else:
        raw = set(clone_choices) - {"__sep1__"}
        clone_options = raw - {"messages"}
        clone_messages = "messages" in raw

    message_limit = 50
    if clone_messages:
        limit_str = await questionary.text(
            "How many messages per channel to clone?",
            default="50",
            style=QSTYLE,
        ).ask_async()
        try:
            message_limit = max(1, min(10000, int(limit_str)))
        except ValueError:
            message_limit = 50

    # ── What to clear from target ─────────────────────────────────────────────
    console.print()
    console.print(Rule("[primary]Step 4 — Clean target server first[/primary]"))
    console.print(
        "  [muted]Choose what to wipe from the target before cloning. Uncheck all to skip cleaning.[/muted]"
    )
    console.print()

    ALL_CLEAR = {"channels", "roles", "emojis", "stickers"}

    clear_choices = await questionary.checkbox(
        "What to delete from the target server first:",
        choices=[
            questionary.Choice("⚡  Clear All",                                               value="clear_all",  checked=False),
            questionary.Choice("─" * 45,                                                       value="__sep2__",   disabled=True),
            questionary.Choice("💬  Channels & Categories",                                  value="channels",   checked=True),
            questionary.Choice("👑  Roles",                                                   value="roles",      checked=True),
            questionary.Choice("😄  Emojis",                                                  value="emojis",     checked=True),
            questionary.Choice("🎨  Stickers",                                                value="stickers",   checked=True),
        ],
        style=QSTYLE,
    ).ask_async()

    if "clear_all" in clear_choices:
        clear_options = ALL_CLEAR.copy()
    else:
        clear_options = set(clear_choices) - {"__sep2__"}


    # ── Confirm ──────────────────────────────────────────────────────────────
    console.print()
    enabled_list = ", ".join(sorted(clone_options)) or "(none)"
    clear_list   = ", ".join(sorted(clear_options)) if clear_options else "Nothing (skip)"
    msg_info     = f"Yes — up to {message_limit}/channel" if clone_messages else "No"
    console.print(
        Panel(
            f"  [label]Source:[/label]          {source_id}\n"
            f"  [label]Target:[/label]          {target_id}\n"
            f"  [label]Will clear:[/label]      {clear_list}\n"
            f"  [label]Will clone:[/label]      {enabled_list}\n"
            f"  [label]Messages:[/label]        {msg_info}",
            title="[primary]Summary[/primary]",
            border_style="#7289DA",
        )
    )

    go = await questionary.confirm(
        "Start cloning?",
        default=True,
        style=QSTYLE,
    ).ask_async()

    if not go:
        console.print("[muted]Aborted.[/muted]")
        sys.exit(0)

    # ── Run cloner ───────────────────────────────────────────────────────────
    console.print()
    console.print(Rule("[primary]Cloning in progress[/primary]"))

    async with DiscordAPI(token) as api:
        cloner = ServerCloner(
            api=api,
            source_id=source_id,
            target_id=target_id,
            clone_options=clone_options,
            clone_messages=clone_messages,
            clear_options=clear_options,
            message_limit=message_limit,
        )
        try:
            await cloner.run()
        except KeyboardInterrupt:
            console.print("\n[warning]Interrupted by user.[/warning]")
        except Exception as e:
            console.print(f"\n[error]Fatal error: {e}[/error]")
            raise

    console.print()
    console.print(
        Panel(
            Align.center("[success]Server cloned successfully! 🎉[/success]"),
            border_style="#43B581",
        )
    )
    console.print()
    await questionary.press_any_key_to_continue(style=QSTYLE).ask_async()


if __name__ == "__main__":
    asyncio.run(main())
