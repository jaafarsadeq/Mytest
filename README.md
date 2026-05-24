# WhatsApp MCP + Phone Notifications

A small Windows-friendly project that:

1. Connects to WhatsApp via **WhatsApp Web** (`whatsapp-web.js`, QR-code login).
2. Stores every incoming message in a local SQLite database.
3. **Pushes every new WhatsApp message to your phone via [ntfy.sh](https://ntfy.sh)**.
4. Exposes an **MCP server** so Claude Desktop can list chats, search messages, and send replies.

Two processes:

- `src/bridge.js` — long-running. WhatsApp Web client + ntfy forwarder + local HTTP API on port 3037.
- `src/mcp-server.js` — short-lived, launched by Claude Desktop over stdio. Talks to the bridge over HTTP.

## Requirements

- Windows 10 / 11
- Node.js 18 or newer (https://nodejs.org)
- A phone running the **ntfy** app (Android: Play Store / F-Droid, iOS: App Store)
- WhatsApp on your phone (to scan the linking QR code)
- *(Optional)* Claude Desktop, if you want the MCP tools

## Setup

```powershell
git clone <this repo>
cd Mytest
npm install
copy .env.example .env
notepad .env
```

In `.env`, set `NTFY_TOPIC` to a hard-to-guess string. Anyone who knows your topic can read your forwarded messages, so treat it like a password. Example: `whatsapp-ji8x29-private-7ab3`.

## Phone setup (ntfy)

1. Install the **ntfy** app on your phone.
2. Open it, tap **+ Subscribe to topic**.
3. Server: `https://ntfy.sh` (default).
4. Topic: the **same** value you set as `NTFY_TOPIC` in `.env`.
5. Allow notifications.

Test it before connecting WhatsApp:

```powershell
curl -d "hello from PC" https://ntfy.sh/YOUR_TOPIC_HERE
```

You should see a notification on your phone within a second or two.

## First run

```powershell
npm run bridge
```

or double-click `start-bridge.bat`.

On first run a QR code is printed in the terminal. On your phone:

> WhatsApp → Settings → Linked Devices → Link a Device → scan the QR

After the scan you should see `[wa] client ready.` Send yourself a WhatsApp message from another phone — within a few seconds your phone gets an ntfy notification.

Session is cached in `data/wa-session`, so subsequent runs don't need a re-scan.

## Filters

In `.env`:

- `ONLY_DIRECT=true` — ignore group messages.
- `MUTE_CHATS=Status@broadcast,Some Noisy Group` — comma-separated chat names or ids to skip.
- `INCLUDE_FROM_ME=true` — also forward messages you send (default off).

## Claude Desktop (MCP) setup

Edit `%APPDATA%\Claude\claude_desktop_config.json` and add:

```json
{
  "mcpServers": {
    "whatsapp": {
      "command": "node",
      "args": ["C:\\path\\to\\Mytest\\src\\mcp-server.js"]
    }
  }
}
```

Restart Claude Desktop. The bridge must already be running (otherwise the MCP tools will return a connection error). Available tools:

| Tool | What it does |
| ---- | ------------ |
| `wa_health` | Check whether bridge is up and WA client is connected |
| `wa_list_chats` | List recent chats, optional name filter |
| `wa_recent_messages` | Most recent messages, optionally for one `chatId` |
| `wa_search_messages` | Substring search across stored messages |
| `wa_send_message` | Send a WhatsApp message to a number or chat id |

## Auto-start on Windows boot (optional)

Easiest: drop a shortcut to `start-bridge.bat` in
`shell:startup` (press Win+R, type `shell:startup`, Enter).

## Deploy to a 24/7 Linux VM

You don't need your PC running — host the bridge on any cheap Linux VM
(DigitalOcean / Hetzner / Oracle Free Tier / your own VPS). 1 vCPU + 1 GB
RAM is enough (Chromium is the heaviest part — add swap if you have only
512 MB).

WhatsApp Multi-Device keeps the linked session alive on Meta's servers,
so your phone does **not** need to be online for the VM to keep receiving
messages.

### Option A — one-shot installer (Ubuntu / Debian)

SSH into the VM as root (or use `sudo`), then:

```bash
curl -fsSL https://raw.githubusercontent.com/jaafarsadeq/Mytest/claude/whatsapp-mcp-notifications-5syJ9/deploy/install-ubuntu.sh | sudo bash
sudo nano /opt/whatsapp-mcp/.env          # set NTFY_TOPIC and PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
sudo systemctl start whatsapp-bridge
sudo journalctl -u whatsapp-bridge -f     # watch logs — scan the QR shown here
```

After you see `[wa] client ready.` you're done — messages flow to your
phone via ntfy.sh. The systemd service auto-restarts on crash and on
reboot.

Useful commands:

```bash
sudo systemctl status whatsapp-bridge    # is it up?
sudo systemctl restart whatsapp-bridge
sudo journalctl -u whatsapp-bridge -f    # follow logs (and re-show QR if needed)
```

If the QR ever needs to be re-scanned (re-linking from your phone wipes
the session), it will reappear in the logs.

### Option B — Docker / docker-compose

```bash
git clone https://github.com/jaafarsadeq/Mytest.git
cd Mytest && git checkout claude/whatsapp-mcp-notifications-5syJ9
cp .env.example .env && nano .env        # set NTFY_TOPIC
docker compose up -d
docker compose logs -f                   # scan QR from these logs on first run
```

The `data/` directory on the host holds both the SQLite DB and the
WhatsApp Web session, so the container can be rebuilt without re-linking.

### Using the MCP server from a different machine

The MCP server is a stdio process — Claude Desktop launches it locally.
If your **bridge** is on a remote VM, you have two options:

**SSH tunnel (simplest, no extra auth)** — on your laptop:

```bash
ssh -N -L 3037:127.0.0.1:3037 user@your-vm
```

Then in `claude_desktop_config.json` point the MCP server at the local
end of the tunnel (it already defaults to `127.0.0.1:3037`).

**Direct, with a token** — on the VM set `BRIDGE_HOST=0.0.0.0` and
`BRIDGE_TOKEN=<long random string>` in `.env`, open port 3037 in the
firewall, and on your laptop run the MCP server with environment
variables:

```json
{
  "mcpServers": {
    "whatsapp": {
      "command": "node",
      "args": ["C:\\path\\to\\Mytest\\src\\mcp-server.js"],
      "env": {
        "BRIDGE_URL": "http://your-vm-ip:3037",
        "BRIDGE_TOKEN": "the-same-token"
      }
    }
  }
}
```

Use the SSH tunnel option unless you know what you're doing — exposing
3037 to the public internet without a token would let anyone send
WhatsApp messages as you.

## Files

- `src/config.js` — env loading
- `src/db.js` — SQLite schema + helpers
- `src/ntfy.js` — ntfy.sh HTTP push
- `src/bridge.js` — WhatsApp Web client + HTTP API + ntfy forwarder
- `src/mcp-server.js` — MCP stdio server, talks to bridge over HTTP
- `data/` — session + SQLite (gitignored)

## Security notes

- The HTTP API listens on `127.0.0.1` only — not reachable from the network.
- Anyone who knows your ntfy topic can read your forwarded messages. Use a long random topic, or self-host ntfy, or set `NTFY_TOKEN` and a protected topic on your server.
- `whatsapp-web.js` is an unofficial library. WhatsApp may flag/ban accounts that misuse it (mass messaging, automation that looks like spam). Personal-use forwarding is generally fine but you're using it at your own risk.
