# AlphaScope 🔭

**AI-powered Crypto KOL monitoring system for OpenClaw**

Monitor 100+ Crypto KOLs on X/Twitter. Filter signal from noise. Track who's actually right.

---

## One-line Install

```bash
curl -fsSL https://raw.githubusercontent.com/GITHUB_USER/alphascope/main/install.sh | bash
```

The installer will:
- Download all scripts
- Install Python dependencies (`twikit`, `playwright`)
- Walk you through config setup interactively
- Run a quick test

---

## What It Does

```
X/Twitter List (your KOLs)
     │
     ▼  every 1h
  Scraper  ──►  #x-realtime   (hourly signal stream)
     │
     ▼  every 6h  
  AI Digest  ──►  #x-digest   (key insights summary)
     │
     ▼  every week
  Alpha Tracker  ──►  #alpha-weekly   (who was actually right?)
```

- **Scrapes** your private X List every hour via cookie auth
- **Filters** noise with a scoring engine (engagement, token mentions, urgency)
- **Summarizes** with Claude AI every 6 hours
- **Tracks** prediction accuracy — turns "KOL alpha" into verifiable data

---

## Requirements

- [OpenClaw](https://docs.openclaw.ai) — installed and connected to Discord
- Python 3.10+
- An X/Twitter account (for cookie auth)
- A Discord server with 3 channels

---

## Configuration

After install, edit these two files:

**`config/system_config.json`** — your IDs and paths (gitignored):
```json
{
  "x": { "list_id": "...", "cookies_path": "..." },
  "discord": { "realtime_channel_id": "...", "digest_channel_id": "..." }
}
```

**`config/user_profiles.json`** — your KOL list (gitignored):
```json
{
  "users": {
    "TwitterHandle": {
      "category": "trader",
      "priority": "high"
    }
  }
}
```

Full setup guide → [INSTALL.md](./INSTALL.md)

---

## Why Not Just Use TweetDeck?

TweetDeck shows you the feed. AlphaScope shows you **who's worth listening to**.

Every call gets logged. Every outcome gets tracked. After a few weeks you have real data on which KOLs' alpha actually converts.

---

*Built on [OpenClaw](https://docs.openclaw.ai) + [twikit](https://github.com/d60/twikit) + Claude*
