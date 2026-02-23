# AlphaScope — KOL Alpha Monitoring System
### Setup Guide for OpenClaw Users

> **What this does**: Monitors a curated list of Crypto KOLs on X/Twitter every hour. Filters signal from noise using AI, tracks who's actually right, and delivers digests to your Discord server.

---

## Architecture Overview

```
X/Twitter List
     │
     ▼ (every 1h via twikit)
list_scraper.py ──► data/history/*.jsonl
                         │
                         ├──► hourly_summary.py ──► #x-realtime / #x-alerts
                         │
                         └──► digest_generator.py (every 6h) ──► #x-digest
                                     │
                                     └──► alpha_tracker.py (weekly) ──► #alpha-weekly
```

**3 Discord channels** you'll need:
- `#x-realtime` — hourly signal stream  
- `#x-digest` — AI-generated 6h summaries
- `#alpha-weekly` — weekly alpha accuracy tracking

---

## Prerequisites

### 1. System Requirements

```bash
# Python 3.10+
python3 --version

# Install dependencies
pip install twikit playwright
playwright install chromium   # optional, for tweet content fetching
```

### 2. OpenClaw
- OpenClaw must be installed and connected to your Discord server
- Cron jobs will use the `message` tool to post to Discord
- Guide: https://docs.openclaw.ai

---

## Step 1 — Get Your X/Twitter Cookies

The scraper authenticates as **your X account** to read List timelines.

### Method A: EditThisCookie (Chrome Extension)
1. Install [EditThisCookie](https://chrome.google.com/webstore/detail/editthiscookie/) extension
2. Log into x.com in Chrome
3. Click the extension → **Export** → copy JSON
4. Save as `~/.openclaw/workspace/.secrets/x_cookies.json`

The cookies file needs these 3 fields:
```json
{
  "auth_token": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "ct0": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "twid": "u%3D123456789"
}
```

> ⚠️ **Cookies expire** every ~30 days or on password change. Re-export when scraping fails.

> 💡 **No cookies?** The system still works in API-only mode for individual tweet fetching, but List scraping requires cookies.

---

## Step 2 — Create Your X KOL List

1. Go to [x.com/lists](https://x.com/lists) → **Create new List**
2. Add the Crypto KOLs you want to monitor
3. Set it to **Private** (recommended — avoids followers noticing)
4. Get the List ID from the URL: `x.com/i/lists/**1869251217303765395**`

---

## Step 3 — Configure the System

```bash
cd ~/.openclaw/workspace/skills/x-cookie-browser
cp config/system_config.example.json config/system_config.json
```

Edit `config/system_config.json`:

```json
{
  "x": {
    "list_id": "YOUR_X_LIST_ID",
    "cookies_path": "/root/.openclaw/workspace/.secrets/x_cookies.json",
    "fetch_count": 100,
    "seen_ids_retention_days": 7
  },
  "discord": {
    "realtime_channel_id": "YOUR_REALTIME_CHANNEL_ID",
    "alerts_channel_id": "YOUR_ALERTS_CHANNEL_ID",
    "digest_channel_id": "YOUR_DIGEST_CHANNEL_ID",
    "alpha_weekly_channel_id": "YOUR_WEEKLY_CHANNEL_ID"
  }
}
```

**How to find Discord Channel IDs:**
1. Enable Developer Mode: Discord Settings → Advanced → Developer Mode ✅
2. Right-click any channel → **Copy Channel ID**

---

## Step 4 — Customize Your KOL Profiles

Edit `config/user_profiles.json` to define your KOL list:

```json
{
  "users": {
    "KOL_TWITTER_HANDLE": {
      "category": "developer",
      "focus": ["AI", "DeFi", "Base"],
      "template": "technical",
      "priority": "high",
      "template_config": {
        "emoji": "📦",
        "sections": ["项目", "技术细节", "影响"]
      }
    }
  }
}
```

**Categories**: `developer`, `trader`, `researcher`, `founder`  
**Templates**: `technical`, `trend`, `alpha`, `news`  
**Priority**: `high`, `medium`, `low` (affects alert threshold)

> Your KOL list in `user_profiles.json` is gitignored by default — it stays private.

---

## Step 5 — Set Up Discord Channels

In your Discord server, create these channels:

| Channel | Purpose | Cron Job |
|:--------|:---------|:---------|
| `#x-realtime` | Hourly signal stream | Every 1h |
| `#x-digest` | AI 6h summaries | Every 6h |
| `#alpha-weekly` | Weekly accuracy report | Sunday 10:00 UTC |

---

## Step 6 — Deploy Cron Jobs

Add these 3 jobs via your OpenClaw session (or directly to `/root/.openclaw/cron/jobs.json`):

### Job 1: Hourly Scraper → #x-realtime

Tell your OpenClaw agent:
```
Set up a cron job called "X-Monitor: Hourly Scrape" that runs every hour.
It should run the script at:
cd ~/.openclaw/workspace/skills/x-cookie-browser/scripts && python3 list_scraper.py && python3 hourly_summary.py

Deliver output to Discord channel: YOUR_REALTIME_CHANNEL_ID
Session: isolated
```

### Job 2: 6-Hour AI Digest → #x-digest

```
Set up a cron job called "X-Monitor: 6H Digest" that runs every 6 hours.
It should run:
cd ~/.openclaw/workspace/skills/x-cookie-browser/scripts && python3 digest_generator.py

Deliver output to Discord channel: YOUR_DIGEST_CHANNEL_ID
Session: isolated
```

### Job 3: Weekly Alpha Tracker → #alpha-weekly

```
Set up a cron job called "Alpha Tracker: Weekly Report" that runs every Sunday at 10:00 UTC.
It should run:
cd ~/.openclaw/workspace/skills/x-cookie-browser/scripts && python3 alpha_tracker.py

Deliver output to Discord channel: YOUR_ALPHA_WEEKLY_CHANNEL_ID
Session: isolated
```

---

## Step 7 — Test Manually

```bash
cd ~/.openclaw/workspace/skills/x-cookie-browser/scripts

# Test scraper (saves to data/history/)
python3 list_scraper.py

# Test hourly summary (reads saved data)
python3 hourly_summary.py

# Test digest generator
python3 digest_generator.py

# Test alpha tracker
python3 alpha_tracker.py
```

Check for output in `data/history/YYYY-MM-DD.jsonl`.

---

## File Structure

```
skills/x-cookie-browser/
├── SKILL.md                     # OpenClaw skill definition
├── INSTALL.md                   # This file
├── .gitignore                   # Excludes private config + data
├── config/
│   ├── system_config.example.json  # Template — commit this ✅
│   ├── system_config.json          # Your config — gitignored 🔒
│   └── user_profiles.json          # Your KOL list — gitignored 🔒
├── data/                           # Runtime data — gitignored 🔒
│   ├── history/YYYY-MM-DD.jsonl    # Daily tweet archives
│   ├── alpha_calls.jsonl           # 30-day alpha call log
│   ├── seen_ids.json               # Dedup cache
│   └── latest_tweets.json          # Last scrape output
└── scripts/
    ├── list_scraper.py             # Main hourly scraper
    ├── hourly_summary.py           # Signal filter + Discord push
    ├── digest_generator.py         # 6h AI summary
    ├── alpha_tracker.py            # Weekly ROI tracker
    ├── filter_agent_v2.py          # Signal scoring engine
    ├── format_agent_v3.py          # Discord message formatter
    ├── x_fetch.py                  # Individual tweet fetcher (CLI)
    ├── dex_utils.py                # Token price lookups
    └── cleanup_history.py          # Old data pruner
```

---

## Troubleshooting

**`list_scraper.py` fails with "list_id not set"**
→ You haven't created `config/system_config.json` yet. Run Step 3.

**Cookies expired / auth error**
→ Re-export cookies from Chrome (Step 1). Replace `x_cookies.json`.

**No tweets appearing**
→ Check that your X List has members and is not empty.  
→ Run `python3 list_scraper.py` manually — check for errors.

**Discord messages not sending**
→ Confirm OpenClaw is running: `openclaw gateway status`  
→ Check channel IDs are correct (use Developer Mode in Discord)

**Alpha tracker shows 0 calls**
→ `alpha_calls.jsonl` builds up over time. Needs ~1 week of data first.

---

## Privacy Notes

- `system_config.json` and `user_profiles.json` are gitignored — your KOL list and credentials stay private
- The system reads your X account's private List — only you can see which KOLs you're tracking
- No data is sent anywhere except your own Discord server via OpenClaw

---

*Built with OpenClaw + twikit + Claude AI*
