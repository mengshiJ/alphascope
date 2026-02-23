#!/usr/bin/env python3
"""
hourly_summary.py - 每小时轻量摘要 + 紧急热点检测
读取 list_scraper.py 产出的 latest_tweets.json，格式化后输出
"""

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dex_utils import lookup_dexscreener, format_dex_info

# === 配置加载（从 system_config.json 读取，fallback 到默认值）===
_SKILL_DIR = Path(__file__).parent.parent
_CONFIG_PATH = _SKILL_DIR / "config" / "system_config.json"

def _load_system_config() -> dict:
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH) as f:
            return json.load(f)
    return {}

_cfg = _load_system_config()
_x_cfg = _cfg.get("x", {})
_data_cfg = _cfg.get("data", {})
_discord_cfg = _cfg.get("discord", {})

DATA_DIR = Path(_data_cfg.get("data_dir") or _SKILL_DIR / "data")
CONFIG_DIR = _SKILL_DIR / "config"
LATEST_PATH = DATA_DIR / "latest_tweets.json"
ALERTS_SENT_PATH = DATA_DIR / "alerts_sent.json"

# Discord 频道 ID（供直接调用时使用）
REALTIME_CHANNEL_ID = _discord_cfg.get("realtime_channel_id", "")
ALERTS_CHANNEL_ID = _discord_cfg.get("alerts_channel_id", "")

# 紧急推送阈值
ALERT_LIKES_THRESHOLD = 500
ALERT_TIME_WINDOW_HOURS = 2

# 合约地址正则
CONTRACT_RE = re.compile(r'0x[a-fA-F0-9]{40}')

# 代币提及正则
TOKEN_RE = re.compile(r'\$([A-Z][A-Z0-9]{1,15})')


def load_latest_tweets() -> dict:
    """加载最新抓取结果"""
    if not LATEST_PATH.exists():
        print("❌ 未找到 latest_tweets.json，请先运行 list_scraper.py")
        sys.exit(1)
    with open(LATEST_PATH) as f:
        return json.load(f)


def load_alerts_sent() -> set:
    """加载已发送的紧急推送 ID"""
    if ALERTS_SENT_PATH.exists():
        with open(ALERTS_SENT_PATH) as f:
            data = json.load(f)
            return set(data.get("sent_ids", []))
    return set()


def save_alerts_sent(sent_ids: set):
    """保存已发送的紧急推送 ID"""
    with open(ALERTS_SENT_PATH, "w") as f:
        json.dump({"sent_ids": list(sent_ids), "updated": datetime.now(timezone.utc).isoformat()}, f)


def load_user_profiles() -> dict:
    """加载用户画像"""
    path = CONFIG_DIR / "user_profiles.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def get_category_emoji(handle: str, profiles: dict) -> str:
    """根据用户画像返回分类 emoji"""
    users = profiles.get("users", {})
    if handle in users:
        cat = users[handle].get("category", "")
        return {
            "developer": "🛠️",
            "kol_cn": "📢",
            "kol_en": "📢",
            "founder": "👑",
        }.get(cat, "📝")
    return "📝"


def detect_co_signals(tweets: list) -> list:
    """检测多人转发/引用同一条推文的情况（共识信号）"""
    groups = defaultdict(list)  # group_key -> list of tweets

    for t in tweets:
        # Case 1: 有明确 retweeted_tweet_id（新字段）
        rtid = t.get("retweeted_tweet_id")
        if rtid:
            groups[f"rt:{rtid}"].append(t)
            continue

        # Case 2: 老数据 fallback — 解析 "RT @handle: ..." 文本
        if t.get("is_retweet") and t["text"].startswith("RT @"):
            m = re.match(r"RT @(\w+): (.{0,60})", t["text"])
            if m:
                key = f"rt_text:{m.group(1)}:{m.group(2)}"
                groups[key].append(t)

    co_signals = []
    for key, group in groups.items():
        if len(group) < 2:
            continue

        # 从 group 中提取原推信息
        sample = group[0]
        orig_author = sample.get("retweeted_handle")
        orig_text = sample.get("retweeted_text")

        # 如果没有新字段，从文本中解析
        if not orig_author and sample["text"].startswith("RT @"):
            m = re.match(r"RT @(\w+): (.+)", sample["text"], re.DOTALL)
            if m:
                orig_author = m.group(1)
                orig_text = m.group(2)

        orig_text = (orig_text or "")[:120]
        orig_tweet_id = sample.get("retweeted_tweet_id")
        orig_url = (
            f"https://x.com/{orig_author}/status/{orig_tweet_id}"
            if orig_author and orig_tweet_id else ""
        )

        co_signals.append({
            "key": key,
            "original_author": orig_author or "?",
            "original_content": orig_text,
            "original_url": orig_url,
            "retweeters": [t["user_handle"] for t in group],
            "count": len(group),
            "max_likes": max(t["likes"] for t in group),
        })

    # 按转发人数降序，人数相同按 likes 降序
    return sorted(co_signals, key=lambda x: (-x["count"], -x["max_likes"]))


def format_co_signal_section(co_signals: list) -> str:
    """格式化多人共识推文区块"""
    if not co_signals:
        return ""

    lines = ["📌 **多人共转** (高共识信号)", ""]
    for sig in co_signals[:5]:  # 最多展示 5 组
        retweeters = " · ".join(f"@{h}" for h in sig["retweeters"][:4])
        count = sig["count"]
        orig_author = sig["original_author"]
        orig_text = re.sub(r'https?://t\.co/\S+', '', sig["original_content"]).strip()[:100]
        orig_url = sig.get("original_url", "")

        lines.append(f"🔺 **{count}人转发** @{orig_author}")
        lines.append(f"  _{orig_text}_")
        lines.append(f"  转发者: {retweeters}")
        if orig_url:
            lines.append(f"  🔗 <{orig_url}>")
        lines.append("")

    return "\n".join(lines)


def format_realtime_summary(tweets: list, profiles: dict) -> str:
    """格式化每小时实时摘要"""
    if not tweets:
        return "📡 **X 监控 - 每小时摘要**\n\n_本周期无新推文_"

    now = datetime.now(timezone.utc)
    lines = [
        f"📡 **X 监控 - 每小时摘要**",
        f"🕐 {now.strftime('%Y-%m-%d %H:%M')} UTC | 新推文 {len(tweets)} 条",
        "",
    ]

    # 提取热门代币
    token_counts = {}
    for t in tweets:
        for tok in t.get("extracted_tokens", []):
            token_counts[tok] = token_counts.get(tok, 0) + 1
    if token_counts:
        top_tokens = sorted(token_counts.items(), key=lambda x: -x[1])[:5]
        tokens_str = " | ".join(f"${tok}({cnt})" for tok, cnt in top_tokens)
        lines.append(f"💰 热门代币: {tokens_str}")
        lines.append("")

    # 多人共转区块（优先展示）
    co_signals = detect_co_signals(tweets)
    if co_signals:
        lines.append(format_co_signal_section(co_signals))
        lines.append("")

    # 按互动排序展示推文（最多 15 条）
    for i, t in enumerate(tweets[:15], 1):
        emoji = get_category_emoji(t["user_handle"], profiles)
        handle = t["user_handle"]
        likes = t["likes"]
        rts = t["retweets"]
        text = t["text"].replace("\n", " ")[:120]

        # 移除 t.co 短链接
        text = re.sub(r'https?://t\.co/\S+', '', text).strip()

        engagement = f"❤️{likes}"
        if rts > 0:
            engagement += f" 🔄{rts}"

        # RT：展示精简版（"转发了 @handle"）
        if t.get("is_retweet"):
            rt_handle = t.get("retweeted_handle")
            rt_text = t.get("retweeted_text", "")
            if rt_handle and rt_text:
                rt_text_clean = re.sub(r'https?://t\.co/\S+', '', rt_text).strip()[:100]
                lines.append(f"{emoji} **@{handle}** 转发了 @{rt_handle} ({engagement})")
                lines.append(f"  _{rt_text_clean}_")
            else:
                # 无新字段，降级展示
                lines.append(f"{emoji} **@{handle}** ({engagement})")
                lines.append(f"  {text}")
        # Quote：展示自己的评论 + 被 quote 的内容
        elif t.get("is_quote"):
            quoted_handle = t.get("quoted_handle")
            quoted_text = t.get("quoted_text", "")
            quoted_tweet_id = t.get("quoted_tweet_id")
            lines.append(f"{emoji} **@{handle}** ({engagement})")
            lines.append(f"  {text}")
            if quoted_handle and quoted_text:
                qt_clean = re.sub(r'https?://t\.co/\S+', '', quoted_text).strip()[:100]
                qt_url = (
                    f"https://x.com/{quoted_handle}/status/{quoted_tweet_id}"
                    if quoted_tweet_id else f"https://x.com/{quoted_handle}"
                )
                lines.append(f"  ↳ 引用 @{quoted_handle}: _{qt_clean}_")
                lines.append(f"  🔗 <{qt_url}>")
        # 普通推文
        else:
            lines.append(f"{emoji} **@{handle}** ({engagement})")
            lines.append(f"  {text}")

        # 显示提及的代币
        tokens = t.get("extracted_tokens", [])
        if tokens:
            lines.append(f"  💰 ${' $'.join(tokens)}")

        # 显示合约地址 + DexScreener 查链
        contracts = t.get("extracted_contracts", [])
        for addr in contracts[:2]:
            lines.append(f"  📜 {format_dex_info(addr)}")

        lines.append("")

    if len(tweets) > 15:
        lines.append(f"_...还有 {len(tweets) - 15} 条推文_")

    return "\n".join(lines)


def detect_alerts(tweets: list, sent_ids: set) -> list:
    """检测紧急热点推文"""
    alerts = []
    now = datetime.now(timezone.utc)

    for t in tweets:
        tid = t["tweet_id"]
        if tid in sent_ids:
            continue

        is_alert = False
        reason = []

        # 高互动检测 — 仅当推文含 crypto 相关内容时才触发
        if t["likes"] >= ALERT_LIKES_THRESHOLD:
            text_lower = t["text"].lower()
            _crypto_kw = ["token", "coin", "crypto", "chain", "defi", "nft",
                          "airdrop", "listing", "launch", "mint", "swap",
                          "yield", "stake", "bridge", "layer", "sol", "eth",
                          "btc", "base", "meme", "dex", "cex", "binance",
                          "代币", "空投", "上币", "合约", "发币", "上线",
                          "挖矿", "质押", "链上"]
            has_tokens = bool(t.get("extracted_tokens")) or bool(t.get("extracted_contracts"))
            has_crypto_kw = any(kw in text_lower for kw in _crypto_kw)
            if has_tokens or has_crypto_kw:
                is_alert = True
                reason.append(f"🔥 高互动 ({t['likes']}❤️)")

        # 新合约地址检测
        if t.get("extracted_contracts"):
            is_alert = True
            reason.append(f"📜 新合约地址")

        # 新代币检测（多个代币提及 + 项目关键词）
        if len(t.get("extracted_tokens", [])) > 0:
            text_lower = t["text"].lower()
            launch_kw = ["launch", "announcing", "new token", "fair launch", "presale",
                         "airdrop", "whitelist", "deployed", "live on"]
            if any(kw in text_lower for kw in launch_kw):
                is_alert = True
                reason.append(f"🆕 新项目/代币发现")

        if is_alert:
            alerts.append({
                **t,
                "alert_reasons": reason,
            })

    return alerts


def format_alert(alert: dict) -> str:
    """格式化单条紧急推送"""
    reasons = " | ".join(alert["alert_reasons"])
    handle = alert["user_handle"]
    text = alert["text"].replace("\n", " ")[:200]
    text = re.sub(r'https?://t\.co/\S+', '', text).strip()
    likes = alert["likes"]
    rts = alert["retweets"]

    lines = [
        f"@here 🚨 **紧急推送** - {reasons}",
        f"",
        f"**@{handle}** | ❤️{likes} 🔄{rts}",
        f"{text}",
    ]

    tokens = alert.get("extracted_tokens", [])
    if tokens:
        lines.append(f"💰 ${' $'.join(tokens)}")

    contracts = alert.get("extracted_contracts", [])
    for addr in contracts[:2]:
        dex_line = format_dex_info(addr)
        lines.append(f"📜 {dex_line}")

    lines.append(f"\n🔗 https://x.com/{handle}/status/{alert['tweet_id']}")
    return "\n".join(lines)


def main():
    """主函数"""
    print("=" * 60)
    print("📡 Hourly Summary Generator")
    print("=" * 60)

    # 加载数据
    data = load_latest_tweets()
    tweets = data.get("tweets", [])
    profiles = load_user_profiles()
    sent_ids = load_alerts_sent()

    print(f"📥 加载推文: {len(tweets)} 条")

    if not tweets:
        # 输出空摘要
        summary = format_realtime_summary([], profiles)
        print("\n--- REALTIME_SUMMARY ---")
        print(summary)
        print("\n--- END ---")
        return

    # 生成实时摘要
    summary = format_realtime_summary(tweets, profiles)
    print(f"📝 生成摘要完成")

    # 检测紧急推送
    alerts = detect_alerts(tweets, sent_ids)
    print(f"🚨 紧急推送: {len(alerts)} 条")

    # 更新已发送 alerts
    for a in alerts:
        sent_ids.add(a["tweet_id"])
    save_alerts_sent(sent_ids)

    # 输出实时摘要（供 cron agent 发送到 #x-realtime）
    print("\n--- REALTIME_SUMMARY ---")
    print(summary)
    print("--- END ---")

    # 输出紧急推送（供 cron agent 发送到 #x-alerts）
    if alerts:
        for alert in alerts:
            print("\n--- ALERT ---")
            print(format_alert(alert))
            print("--- END ---")

    print(f"\n✅ 完成")


if __name__ == "__main__":
    main()
