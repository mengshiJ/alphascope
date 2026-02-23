#!/usr/bin/env python3
"""
digest_generator.py - 每6小时 AI 精华总结
读取最近6小时的历史数据，生成 Claude prompt，输出中文精华摘要
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# === 配置 ===
DATA_DIR = Path("/root/.openclaw/workspace/skills/x-cookie-browser/data")
CONFIG_DIR = Path("/root/.openclaw/workspace/skills/x-cookie-browser/config")
HISTORY_DIR = DATA_DIR / "history"

# 读取最近多少小时的数据
DIGEST_HOURS = 6


def load_recent_tweets(hours: int = DIGEST_HOURS) -> list:
    """从历史文件加载最近 N 小时的推文"""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    tweets = []

    # 可能跨天，检查所有涉及的日期
    dates_to_check = set()
    d = cutoff.date()
    end = now.date()
    while d <= end:
        dates_to_check.add(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)

    for date_str in sorted(dates_to_check):
        path = HISTORY_DIR / f"{date_str}.jsonl"
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    tweet = json.loads(line)
                    tweets.append(tweet)
                except json.JSONDecodeError:
                    continue

    # 去重（同一推文可能在多次抓取中出现）
    seen = set()
    unique = []
    for t in tweets:
        tid = t.get("tweet_id")
        if tid and tid not in seen:
            seen.add(tid)
            unique.append(t)

    # 按互动排序
    unique.sort(key=lambda t: t.get("likes", 0) + t.get("retweets", 0) * 2, reverse=True)
    return unique


def load_user_profiles() -> dict:
    """加载用户画像"""
    path = CONFIG_DIR / "user_profiles.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def build_digest_prompt(tweets: list, profiles: dict) -> str:
    """构建 Claude 总结的 prompt"""
    now = datetime.now(timezone.utc)
    period_start = (now - timedelta(hours=DIGEST_HOURS)).strftime("%H:%M")
    period_end = now.strftime("%H:%M")

    # 准备推文数据摘要（限制 token 量）
    tweet_summaries = []
    for i, t in enumerate(tweets[:50]):  # 最多 50 条
        handle = t.get("user_handle", "unknown")
        text = t.get("text", "")[:300]
        likes = t.get("likes", 0)
        rts = t.get("retweets", 0)
        tokens = t.get("extracted_tokens", [])
        contracts = t.get("extracted_contracts", [])

        # 获取用户分类
        user_info = profiles.get("users", {}).get(handle, {})
        category = user_info.get("category", "unknown")

        summary = f"[@{handle}] (类型:{category}, likes:{likes} rt:{rts}): {text}"
        if tokens:
            summary += f" | 代币: ${', $'.join(tokens)}"
        if contracts:
            summary += f" | 合约: {contracts[0][:20]}..."
        tweet_summaries.append(summary)

    tweets_text = "\n".join(tweet_summaries)

    prompt = f"""你是一个 Crypto/Web3 领域的中文分析师。请根据以下过去 {DIGEST_HOURS} 小时（{period_start}-{period_end} UTC）的 X/Twitter 推文数据，生成一份精华摘要。

## 推文数据（共 {len(tweets)} 条，按互动量排序）

{tweets_text}

## 输出要求

请生成以下格式的中文精华摘要：

### 📊 X 监控精华 | {now.strftime('%Y-%m-%d %H:%M')} UTC

**⏰ 时间范围**: 过去 {DIGEST_HOURS} 小时 | 共收录 {len(tweets)} 条推文

#### 🔥 热门话题聚合
（将多人讨论的同一话题合并，列出 3-5 个热门话题，每个包含相关用户和核心观点）

#### 🆕 新项目/代币发现
（列出发现的新项目、新代币、新合约，包含关键信息和风险提示）

#### 💡 重要观点提炼
（提炼 KOL 和开发者的重要观点，特别关注行情预测、技术趋势、行业洞察）

#### 🏆 Top 5 推文精选
（选出互动最高或内容最有价值的 5 条推文，简要说明推荐原因）

## 注意事项
- 使用中文输出
- 保持客观，对于行情预测标注"仅供参考"
- 合约地址和代币名称要准确引用
- 如果数据中有明显的 FOMO/诈骗迹象，请标注风险提示
- 总字数控制在 800-1200 字"""

    return prompt


def main():
    """主函数"""
    print("=" * 60)
    print("📊 Digest Generator (6-hourly AI Summary)")
    print("=" * 60)

    # 加载数据
    tweets = load_recent_tweets()
    profiles = load_user_profiles()

    print(f"📥 最近 {DIGEST_HOURS} 小时推文: {len(tweets)} 条")

    if not tweets:
        print("⚠️ 无推文数据，跳过生成")
        now = datetime.now(timezone.utc)
        print("\n--- DIGEST ---")
        print(f"### 📊 X 监控精华 | {now.strftime('%Y-%m-%d %H:%M')} UTC")
        print(f"\n_过去 {DIGEST_HOURS} 小时无新推文数据_")
        print("--- END ---")
        return

    # 构建 prompt
    prompt = build_digest_prompt(tweets, profiles)

    # 统计信息
    all_tokens = set()
    all_handles = set()
    for t in tweets:
        all_tokens.update(t.get("extracted_tokens", []))
        all_handles.add(t.get("user_handle", ""))

    print(f"👥 涉及用户: {len(all_handles)} 人")
    if all_tokens:
        print(f"💰 代币提及: {', '.join(sorted(all_tokens)[:10])}")

    # 输出 prompt（供 cron agent 的 Claude 模型处理）
    print("\n--- DIGEST_PROMPT ---")
    print(prompt)
    print("--- END ---")

    # 同时输出原始数据摘要，供 agent 参考
    print("\n--- TOP_TWEETS_JSON ---")
    top5 = tweets[:5]
    print(json.dumps(top5, ensure_ascii=False, indent=2))
    print("--- END ---")

    print(f"\n✅ Prompt 生成完成 ({len(prompt)} 字符)")


if __name__ == "__main__":
    main()
