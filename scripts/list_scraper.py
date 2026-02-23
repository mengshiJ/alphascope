#!/usr/bin/env python3
"""
list_scraper.py - X List Timeline 抓取 + 去重 + 持久化
使用 twikit cookie 认证，一次请求抓取整个 List timeline
"""

import asyncio
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from twikit import Client

# === 配置加载 ===
# 优先读取 config/system_config.json，fallback 到默认值
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

COOKIES_PATH = Path(_x_cfg.get("cookies_path", "~/.secrets/x_cookies.json")).expanduser()
DATA_DIR = Path(_data_cfg.get("data_dir") or _SKILL_DIR / "data")
HISTORY_DIR = DATA_DIR / "history"
ALPHA_CALLS_PATH = DATA_DIR / "alpha_calls.jsonl"

LIST_ID = _x_cfg.get("list_id", "")
if not LIST_ID:
    raise RuntimeError("❌ list_id not set! Copy config/system_config.example.json → config/system_config.json and fill in your X List ID.")

FETCH_COUNT = _x_cfg.get("fetch_count", 100)

# 去重保留天数
SEEN_IDS_RETENTION_DAYS = _x_cfg.get("seen_ids_retention_days", 7)


def load_cookies() -> dict:
    """加载 X cookies"""
    with open(COOKIES_PATH) as f:
        return json.load(f)


def load_seen_ids() -> dict:
    """加载已见 tweet_id 集合（带时间戳，用于过期清理）"""
    path = DATA_DIR / "seen_ids.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def save_seen_ids(seen: dict):
    """保存已见 tweet_id 集合"""
    path = DATA_DIR / "seen_ids.json"
    with open(path, "w") as f:
        json.dump(seen, f)


def clean_expired_ids(seen: dict) -> dict:
    """清理超过保留期限的 tweet_id"""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=SEEN_IDS_RETENTION_DAYS)).isoformat()
    return {tid: ts for tid, ts in seen.items() if ts > cutoff}


def parse_tweet(tweet) -> dict:
    """解析 twikit Tweet 对象为字典"""
    text = tweet.text or ""

    # 提取代币提及 — 三层识别：$TOKEN, #TOKEN, 上下文感知的裸词
    _STOP = {"THE","AND","FOR","THIS","THAT","WITH","FROM","HAVE",
             "BEEN","WILL","NOT","BUT","ALL","CAN","HER","HIS",
             "ONE","OUR","OUT","ARE","WAS","HAS","ITS","INTO",
             "WHO","HOW","WHY","ANY","MAY","NOW","NEW","OLD",
             "BIG","DAY","WAY","GET","GOT","SET","LET","SAY",
             "USE","SEE","TWO","FEW","USD","EUR","GBP",
             # 常见非代币缩写
             "RT","DM","CEO","CTO","CFO","COO","IMO","TBH","FYI",
             "OMG","WTF","IDK","BTW","ASAP","FAQ","DIY","RIP",
             "API","URL","PDF","SQL","CSS","HTML","JSON","SDK",
             "SEC","NYSE","IPO","ETF","GDP","CPI","FED","FOMC",
             "VC","PE","LP","GP","KOL","OG","PFP","GM","GN",
             "LFG","WAGMI","NGMI","NFA","DYOR","HODL",
             "ERC","WL","TGE","IDO","ICO","IEO",
             "UX","UI","MVP","POC","TLD","LLM",
             "NVIDIA","APPLE","GOOGLE","META","TESLA",
             # call 上下文中的常见英语噪音词
             "ARMY","ROLL","CALL","HOLD","SELL","BUY","LONG",
             "SHORT","MOON","PUMP","DUMP","BURN","MINT","SWAP",
             "FARM","POOL","LOCK","DROP","SEND","BACK","JUST",
             "LIKE","GOOD","BEST","MORE","MOST","MUCH","VERY",
             "REAL","LIVE","OPEN","HIGH","LOW","TOP","UP","DOWN"}

    # Layer 1: $TOKEN（最高置信度）
    _dollar_en = re.findall(r'\$([A-Za-z][A-Za-z0-9]{1,15})', text)
    _dollar_cn = re.findall(r'\$([\u4e00-\u9fff]{1,10})', text)

    # Layer 2: #TOKEN（中等置信度）
    _hash_en = re.findall(r'#([A-Za-z][A-Za-z0-9]{1,10})', text)
    _hash_cn = re.findall(r'#([\u4e00-\u9fff]{1,10})', text)

    # Layer 3: 裸词大写（低置信度，需要 call 上下文）
    _CALL_KEYWORDS = ["call","冲","看好","入了","买了","上车","梭哈","建仓",
                      "加仓","抄底","埋伏","布局","龙头","翻倍","拉盘",
                      "起飞","暴涨","做多","开多","抢跑","偷跑"]
    _text_lower = text.lower()
    _has_call_ctx = any(kw in _text_lower for kw in _CALL_KEYWORDS)
    _bare_en = []
    if _has_call_ctx:
        # 匹配不跟在 $ # @ 后面的全大写 2-10 字符词
        _bare_en = re.findall(r'(?<![\$#@\w])([A-Z][A-Z0-9]{1,9})(?!\w)', text)

    # 合并去重（$优先 > # > 裸词），过滤停用词
    seen_tokens = set()
    tokens = []
    for t in _dollar_en + _hash_en + _bare_en:
        up = t.upper()
        if up not in _STOP and up not in seen_tokens and len(t) >= 2:
            tokens.append(up)
            seen_tokens.add(up)
    for t in _dollar_cn + _hash_cn:
        if t not in seen_tokens:
            tokens.append(t)
            seen_tokens.add(t)

    # 提取合约地址
    contracts = re.findall(r'0x[a-fA-F0-9]{40}', text)

    # 提取 URLs
    urls = []
    if tweet.urls:
        for u in tweet.urls:
            if isinstance(u, dict):
                urls.append(u.get("expanded_url", u.get("url", "")))
            elif isinstance(u, str):
                urls.append(u)
            else:
                urls.append(str(u))

    # 提取媒体
    media = []
    if tweet.media:
        for m in tweet.media:
            if isinstance(m, dict):
                media.append({"type": m.get("type", "unknown"), "url": m.get("media_url_https", "")})
            else:
                media.append({"type": getattr(m, "type", "unknown"), "url": getattr(m, "media_url_https", "")})

    # 捕获 RT 原推 ID（用于多人共转聚合）
    retweeted_tweet_id = None
    retweeted_handle = None
    retweeted_text = None
    if tweet.retweeted_tweet:
        rt = tweet.retweeted_tweet
        retweeted_tweet_id = rt.id
        retweeted_handle = rt.user.screen_name if rt.user else None
        retweeted_text = (rt.text or "")[:200]

    # 捕获 Quote 原推内容（twikit: tweet.quote or tweet.quoted_tweet）
    quoted_tweet_id = None
    quoted_handle = None
    quoted_text = None
    qt = getattr(tweet, "quote", None) or getattr(tweet, "quoted_tweet", None)
    if qt:
        quoted_tweet_id = qt.id
        quoted_handle = qt.user.screen_name if getattr(qt, "user", None) else None
        quoted_text = (qt.text or "")[:200]

    return {
        "tweet_id": tweet.id,
        "user_handle": tweet.user.screen_name if tweet.user else "unknown",
        "user_name": tweet.user.name if tweet.user else "unknown",
        "text": text,
        "created_at": tweet.created_at,
        "likes": tweet.favorite_count or 0,
        "retweets": tweet.retweet_count or 0,
        "replies": tweet.reply_count or 0,
        "views": tweet.view_count if tweet.view_count else 0,
        "is_retweet": bool(tweet.retweeted_tweet),
        "is_quote": bool(getattr(tweet, "is_quote_status", False)),
        # RT 原推信息（多人转发聚合用）
        "retweeted_tweet_id": retweeted_tweet_id,
        "retweeted_handle": retweeted_handle,
        "retweeted_text": retweeted_text,
        # Quote 原推信息（展示被 quote 的内容）
        "quoted_tweet_id": quoted_tweet_id,
        "quoted_handle": quoted_handle,
        "quoted_text": quoted_text,
        "extracted_tokens": tokens,
        "extracted_contracts": contracts,
        "extracted_urls": urls,
        "media": media,
    }


def append_to_history(tweets: list):
    """追加推文到每日历史文件（JSONL 格式）"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = HISTORY_DIR / f"{today}.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        for t in tweets:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")


# === Alpha Call 追踪 ===

def load_known_contracts() -> set:
    """从 alpha_calls.jsonl 加载已知合约地址，避免重复记录"""
    known = set()
    if ALPHA_CALLS_PATH.exists():
        with open(ALPHA_CALLS_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    known.add(rec.get("contract", "").lower())
                except json.JSONDecodeError:
                    continue
    return known


def append_alpha_call(call_dict: dict):
    """追加一条 alpha call 记录到 JSONL"""
    with open(ALPHA_CALLS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(call_dict, ensure_ascii=False) + "\n")


def load_known_tweet_ids() -> set:
    """从 alpha_calls.jsonl 加载已记录的 tweet_id，避免重复"""
    known = set()
    if ALPHA_CALLS_PATH.exists():
        with open(ALPHA_CALLS_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line.strip())
                    known.add(rec.get("tweet_id", ""))
                    known.add(rec.get("contract", "").lower())
                except Exception:
                    continue
    return known


# 主流大币 — 不作为 alpha call 追踪，太常见
_MAJOR_TOKENS = {
    "BTC","ETH","SOL","XRP","BNB","USDT","USDC","DAI","MATIC",
    "AVAX","DOT","ADA","DOGE","SHIB","LTC","LINK","UNI","AAVE",
    "OP","ARB","SUI","APT","TRX","TON","NEAR","ATOM","FIL",
    "BITCOIN","ETHEREUM","SOLANA","RIPPLE","CARDANO",
}

# 买入/看涨信号关键词
_BULLISH_KW = {
    "buy","long","bullish","entry","accumulate","load","gem","alpha",
    "ape","degen","early","launch","fair launch","just launched",
    "new token","contract","call","100x","1000x","moon","pump",
    "买","做多","入场","看涨","抄底","喊单","发现","新币","合约",
}


def record_alpha_calls(new_tweets: list):
    """记录 alpha call：CA 地址 + 小币 symbol 喊单"""
    from dex_utils import lookup_dexscreener

    known = load_known_tweet_ids()
    now_iso = datetime.now(timezone.utc).isoformat()
    recorded = 0

    for tweet in new_tweets:
        tid = tweet.get("tweet_id", "")
        text_lower = tweet.get("text", "").lower()

        # ── 路径1：有 CA 地址 ──────────────────────────────
        for addr in tweet.get("extracted_contracts", []):
            addr_lower = addr.lower()
            if addr_lower in known:
                continue

            dex_info = lookup_dexscreener(addr)
            snapshot = None
            if dex_info:
                snapshot = {
                    "chain": dex_info.get("chain", "?"),
                    "symbol": dex_info.get("symbol", "?"),
                    "price_usd": dex_info.get("price_usd"),
                    "market_cap": dex_info.get("market_cap"),
                    "liquidity_usd": dex_info.get("liquidity_usd"),
                    "volume_24h": dex_info.get("volume_24h"),
                }

            call_record = {
                "call_id": f"{tid}:{addr}",
                "tweet_id": tid,
                "user_handle": tweet["user_handle"],
                "call_type": "ca",
                "contract": addr,
                "tokens_mentioned": tweet.get("extracted_tokens", []),
                "text_snippet": tweet["text"][:200],
                "discovered_at": now_iso,
                "discovery_snapshot": snapshot,
            }
            append_alpha_call(call_record)
            known.add(addr_lower)
            recorded += 1
            sym = dex_info["symbol"] if dex_info else "?"
            print(f"  📈 CA call: @{tweet['user_handle']} → ${sym} ({addr[:10]}...)")

        # ── 路径2：小币 symbol 喊单（无 CA）──────────────────
        # 条件：有非主流代币 + 含看涨关键词，且本推文未记录过
        if tid in known:
            continue

        small_tokens = [
            t for t in tweet.get("extracted_tokens", [])
            if t.upper() not in _MAJOR_TOKENS and len(t) >= 2
        ]
        if not small_tokens:
            continue

        has_bullish = any(kw in text_lower for kw in _BULLISH_KW)
        if not has_bullish:
            continue

        # 尝试 DexScreener symbol 搜索
        snapshot = None
        try:
            import requests
            for sym in small_tokens[:2]:
                r = requests.get(
                    f"https://api.dexscreener.com/latest/dex/search?q={sym}",
                    timeout=5
                )
                pairs = r.json().get("pairs", [])
                if pairs:
                    p = pairs[0]
                    snapshot = {
                        "chain": p.get("chainId", "?"),
                        "symbol": sym,
                        "price_usd": float(p.get("priceUsd", 0) or 0),
                        "market_cap": p.get("fdv"),
                        "liquidity_usd": p.get("liquidity", {}).get("usd"),
                        "volume_24h": p.get("volume", {}).get("h24"),
                    }
                    break
        except Exception:
            pass

        call_record = {
            "call_id": f"{tid}:token",
            "tweet_id": tid,
            "user_handle": tweet["user_handle"],
            "call_type": "symbol",
            "contract": None,
            "tokens_mentioned": small_tokens,
            "text_snippet": tweet["text"][:200],
            "discovered_at": now_iso,
            "discovery_snapshot": snapshot,
        }
        append_alpha_call(call_record)
        known.add(tid)
        recorded += 1
        print(f"  📣 Symbol call: @{tweet['user_handle']} → ${', $'.join(small_tokens)}")

    if recorded:
        print(f"📊 记录 {recorded} 个新 alpha call")
    return recorded


async def scrape_list():
    """主抓取逻辑"""
    print("=" * 60)
    print("🔄 X List Timeline Scraper (twikit cookie-based)")
    print("=" * 60)

    # 初始化 twikit client
    client = Client(language="en-US")
    cookies = load_cookies()
    client.set_cookies({
        "auth_token": cookies["auth_token"],
        "ct0": cookies["ct0"],
    })
    print(f"✅ Cookie 认证已设置")

    # 加载已见 ID
    seen = load_seen_ids()
    seen = clean_expired_ids(seen)
    print(f"📋 已见 tweet_id: {len(seen)} 条（清理过期后）")

    # 抓取 List timeline
    print(f"📡 抓取 List {LIST_ID} (count={FETCH_COUNT})...")
    try:
        result = await client.get_list_tweets(LIST_ID, count=FETCH_COUNT)
    except Exception as e:
        print(f"❌ 抓取失败: {e}")
        sys.exit(1)

    tweets_raw = list(result)
    print(f"📥 获取推文: {len(tweets_raw)} 条")

    # 解析 + 去重
    now_iso = datetime.now(timezone.utc).isoformat()
    new_tweets = []
    for tweet in tweets_raw:
        parsed = parse_tweet(tweet)
        tid = parsed["tweet_id"]
        if tid not in seen:
            new_tweets.append(parsed)
            seen[tid] = now_iso

    print(f"🆕 新推文: {len(new_tweets)} 条（去重后）")

    # 按互动量排序
    new_tweets.sort(key=lambda t: t["likes"] + t["retweets"] * 2, reverse=True)

    # 保存 latest_tweets.json
    output = {
        "timestamp": now_iso,
        "list_id": LIST_ID,
        "total_fetched": len(tweets_raw),
        "new_count": len(new_tweets),
        "tweets": new_tweets,
    }
    latest_path = DATA_DIR / "latest_tweets.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"💾 保存到: {latest_path}")

    # 追加到历史
    if new_tweets:
        append_to_history(new_tweets)
        print(f"📝 追加到历史记录")

    # === Alpha Call 追踪 ===
    if new_tweets:
        has_contracts = any(t.get("extracted_contracts") for t in new_tweets)
        if has_contracts:
            print(f"🔍 检测到合约地址，记录 alpha call...")
            record_alpha_calls(new_tweets)

    # 保存 seen_ids
    save_seen_ids(seen)
    print(f"📋 更新 seen_ids: {len(seen)} 条")

    # 统计
    if new_tweets:
        all_tokens = set()
        all_contracts = set()
        for t in new_tweets:
            all_tokens.update(t["extracted_tokens"])
            all_contracts.update(t["extracted_contracts"])
        if all_tokens:
            print(f"💰 代币提及: {', '.join(sorted(all_tokens))}")
        if all_contracts:
            print(f"📜 合约地址: {len(all_contracts)} 个")
        top = new_tweets[0]
        print(f"🔥 最热推文: @{top['user_handle']} ({top['likes']}❤️) - {top['text'][:80]}...")

    print("=" * 60)
    print(f"✅ 完成！新推文 {len(new_tweets)} 条")
    return new_tweets


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(scrape_list())
    # 输出 JSON 供 pipeline 下游使用
    print("\n--- JSON OUTPUT ---")
    print(json.dumps({"new_count": len(result)}, ensure_ascii=False))
