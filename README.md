# GREJ Server Cloner — Selfbot

A Python selfbot that clones a Discord server's full structure into a target server you own.

> ⚠️ **Selfbots violate Discord's Terms of Service.** This tool is for educational/research purposes only. Use at your own risk.

---

## Features

| Feature | Supported |
|---|---|
| Server name, icon, banner, splash | ✅ |
| Roles (color, permissions, hoist) | ✅ |
| Categories | ✅ |
| Text channels (topic, slowmode, NSFW) | ✅ |
| Voice channels (bitrate, user limit) | ✅ |
| Channel permission overwrites | ✅ |
| Emojis (static + animated) | ✅ |
| Message cloning (via webhooks) | ✅ (opt-in) |
| Clear target server before cloning | ✅ (opt-in, default ON) |

---

## Requirements

- Python 3.11+
- A Discord **user token** (not a bot token)
- Admin/Owner access on the **target** server
- Regular member access (View Channels) on the **source** server is enough

---

## Installation

```bash
cd "Discord Cloner"
pip install -r requirements.txt
```

---

## Usage

```bash
python main.py
```

The interactive TUI will guide you through:
1. Entering your user token (saved to `config.json` for reuse)
2. Entering the source & target server IDs
3. Choosing options (clear target, clone messages)
4. Confirming and running

### Getting Your Token

1. Open Discord in your browser (discord.com)
2. Press `F12` → Console tab
3. Paste: `webpackChunkdiscord_app.push([[Math.random()],{},e=>{m=[];for(let c in e.c)m.push(e.c[c])}]);m.filter(m=>m?.exports?.default?.getToken!==void 0).map(m=>m.exports.default.getToken())`
4. Copy the returned string — that's your token

### Getting Server IDs

1. Open Discord Settings → Advanced → Enable **Developer Mode**
2. Right-click any server icon → **Copy Server ID**

---

## File Structure

```
Discord Cloner/
├── main.py          # Entry point + TUI
├── cloner.py        # Cloning logic
├── api.py           # Discord REST wrapper
├── config.json      # Saved token & settings (auto-created)
└── requirements.txt
```

---

## Notes

- Rate limits are handled automatically (the tool waits and retries)
- If you only have **View Channels** access on the source, you'll get everything visible to you — channels, roles, emojis, and messages
- The `config.json` stores your token locally — keep it safe and don't share it
