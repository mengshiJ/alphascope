#!/usr/bin/env python3
"""
alpha_tracker.py - Alpha Call 周度分析 + 用户评分
读取 data/alpha_calls.jsonl，重查 DexScreener 当前价格，
计算 ROI、按用户聚合评分、生成 Markdown 报告。
"""

import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dex_utils import lookup_dexscreener, format_number

# === 配置加载（从 system_config.json 读取，fallback 到默认值）===
_SKILL_DIR = Path(__file__).parent.parent
_CONFIG_PATH = _SKILL_DIR / "config" / "system_config.json"

def _load_system_config() -> dict:
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH) as f:
            return json.load(f)
    return {}

_cfg = _load_system_config()
_data_cfg = _cfg.get("data", {})
_discord_cfg = _cfg.get("discord", {})

DATA_DIR = Path(_data_cfg.get("data_dir") or _SKILL_DIR / "data")
ALPHA_CALLS_PATH = DATA_DIR / "alpha_calls.jsonl"
ALPHA_WEEKLY_CHANNEL_ID = _discord_cfg.get("alpha_weekly_channel_id", "")

# DexScreener API rate limit: ~300 req/min, 加 delay 保险
DEX_QUERY_DELAY = 0.3  # 秒


def load_alpha_calls() -> list[dict]:
    """读取全部 alpha call 记录"""
    calls = []
    if not ALPHA_CALLS_PATH.exists():
        return calls
    with open(ALPHA_CALLS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                calls.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return calls


def compute_roi(discovery_price: str | float | None, current_price: str | float | None) -> float | None:
    """计算 ROI: (current - discovery) / discovery"""
    try:
        d = float(discovery_price)
        c = float(current_price)
        if d <= 0:
            return None
        return (c - d) / d
    except (TypeError, ValueError):
        return None


def normalize(values: list[float]) -> list[float]:
    """Min-max 归一化到 [0, 1]"""
    if not values:
        return []
    mn, mx = min(values), max(values)
    if mx == mn:
        return [0.5] * len(values)
    return [(v - mn) / (mx - mn) for v in values]


def analyze_calls(calls: list[dict]) -> dict:
    """
    对每个 call 重查 DexScreener，计算 ROI，按用户聚合。

    Returns:
        {
            "calls_with_roi": [...],     # 每个 call 加上 current_snapshot + roi
            "user_stats": {...},          # user_handle -> aggregated stats
            "user_ranking": [...],        # sorted list of (handle, stats)
            "best_calls": [...],          # top 5 by ROI
            "worst_calls": [...],         # bottom 5 by ROI
        }
    """
    print(f"📊 分析 {len(calls)} 个 alpha call...")

    # 去重合约（只查一次 DexScreener）
    unique_contracts = {}
    for c in calls:
        addr = c.get("contract", "").lower()
        if addr and addr not in unique_contracts:
            unique_contracts[addr] = None

    # 批量查询当前价格
    print(f"🔍 查询 {len(unique_contracts)} 个合约的当前价格...")
    for i, addr in enumerate(unique_contracts):
        info = lookup_dexscreener(addr)
        unique_contracts[addr] = info
        if (i + 1) % 10 == 0:
            print(f"  ... {i+1}/{len(unique_contracts)} done")
        time.sleep(DEX_QUERY_DELAY)

    # 计算每个 call 的 ROI
    calls_with_roi = []
    for c in calls:
        addr = c.get("contract", "").lower()
        snapshot = c.get("discovery_snapshot")
        current = unique_contracts.get(addr)

        discovery_price = snapshot.get("price_usd") if snapshot else None
        current_price = current.get("price_usd") if current else None
        roi = compute_roi(discovery_price, current_price)

        discovery_mcap = snapshot.get("market_cap") if snapshot else None
        current_mcap = current.get("market_cap") if current else None

        calls_with_roi.append({
            **c,
            "current_snapshot": {
                "chain": current.get("chain", "?") if current else "?",
                "symbol": current.get("symbol", "?") if current else "?",
                "price_usd": current_price,
                "market_cap": current_mcap,
                "liquidity_usd": current.get("liquidity_usd") if current else None,
            } if current else None,
            "roi": roi,
            "discovery_mcap": discovery_mcap,
            "current_mcap": current_mcap,
        })

    # 按用户聚合
    user_calls = defaultdict(list)
    for c in calls_with_roi:
        user_calls[c["user_handle"]].append(c)

    user_stats = {}
    for handle, ucalls in user_calls.items():
        rois = [c["roi"] for c in ucalls if c["roi"] is not None]
        mcaps = [c["discovery_mcap"] for c in ucalls if c.get("discovery_mcap")]

        total = len(ucalls)
        wins = sum(1 for r in rois if r > 0)
        win_rate = wins / len(rois) if rois else 0
        avg_roi = sum(rois) / len(rois) if rois else 0
        best_roi = max(rois) if rois else 0
        avg_mcap = sum(mcaps) / len(mcaps) if mcaps else 0

        # 找最佳 call
        best_call = None
        if rois:
            best_idx = rois.index(max(rois))
            roi_calls = [c for c in ucalls if c["roi"] is not None]
            if roi_calls:
                best_call = roi_calls[best_idx] if best_idx < len(roi_calls) else None

        user_stats[handle] = {
            "total_calls": total,
            "tracked_calls": len(rois),  # 有 ROI 数据的
            "win_rate": win_rate,
            "avg_roi": avg_roi,
            "best_roi": best_roi,
            "best_call": best_call,
            "avg_discovery_mcap": avg_mcap,
        }

    # 综合评分
    handles = list(user_stats.keys())
    if handles:
        wr_vals = [user_stats[h]["win_rate"] for h in handles]
        roi_vals = [user_stats[h]["avg_roi"] for h in handles]
        mcap_vals = [1.0 / max(user_stats[h]["avg_discovery_mcap"], 1) for h in handles]
        call_vals = [float(user_stats[h]["total_calls"]) for h in handles]

        wr_norm = normalize(wr_vals)
        roi_norm = normalize(roi_vals)
        mcap_norm = normalize(mcap_vals)
        call_norm = normalize(call_vals)

        for i, h in enumerate(handles):
            score = (
                wr_norm[i] * 0.4
                + roi_norm[i] * 0.3
                + mcap_norm[i] * 0.2
                + call_norm[i] * 0.1
            )
            user_stats[h]["score"] = score

    # 排名
    user_ranking = sorted(
        [(h, s) for h, s in user_stats.items()],
        key=lambda x: x[1].get("score", 0),
        reverse=True,
    )

    # 最佳 / 最差 call
    valid_roi_calls = [c for c in calls_with_roi if c["roi"] is not None]
    best_calls = sorted(valid_roi_calls, key=lambda c: c["roi"], reverse=True)[:5]
    worst_calls = sorted(valid_roi_calls, key=lambda c: c["roi"])[:5]

    return {
        "calls_with_roi": calls_with_roi,
        "user_stats": user_stats,
        "user_ranking": user_ranking,
        "best_calls": best_calls,
        "worst_calls": worst_calls,
    }


def generate_report(result: dict) -> str:
    """生成 Markdown 周报"""
    now = datetime.now(timezone.utc)
    calls = result["calls_with_roi"]
    ranking = result["user_ranking"]
    best = result["best_calls"]
    worst = result["worst_calls"]

    total_calls = len(calls)
    total_users = len(ranking)
    tracked = sum(1 for c in calls if c["roi"] is not None)

    lines = [
        f"📊 **Alpha Tracker 周报** | {now.strftime('%Y-%m-%d')}",
        "",
        f"📈 追踪 Call: {total_calls} 个合约 / {total_users} 位用户 (有价格数据: {tracked})",
        "",
    ]

    # 用户排名
    if ranking:
        lines.append("🏆 **用户排名**")
        for i, (handle, stats) in enumerate(ranking[:10], 1):
            wr = f"{stats['win_rate']:.0%}"
            avg = f"{stats['avg_roi']:+.0%}"
            total = stats["total_calls"]
            best_roi_str = f"{stats['best_roi']:+.0%}" if stats["best_roi"] else "N/A"

            best_call = stats.get("best_call")
            best_symbol = ""
            if best_call:
                snap = best_call.get("discovery_snapshot") or {}
                best_symbol = f", 最佳 ${snap.get('symbol', '?')} {best_roi_str}"

            lines.append(
                f"{i}. @{handle} — {total} calls, WR {wr}, "
                f"平均 ROI {avg}{best_symbol}"
            )
        lines.append("")

    # 最佳 Call
    if best:
        lines.append("🔥 **最佳 Call**")
        for c in best:
            handle = c["user_handle"]
            snap = c.get("discovery_snapshot") or {}
            symbol = snap.get("symbol", "?")
            chain = snap.get("chain", "?")
            d_mcap = c.get("discovery_mcap")
            c_mcap = c.get("current_mcap")
            roi = c["roi"]

            d_str = format_number(d_mcap) if d_mcap else "?"
            c_str = format_number(c_mcap) if c_mcap else "?"

            lines.append(
                f"  @{handle}: ${symbol} ({chain}) — "
                f"发现时 MC {d_str} → 现在 {c_str} ({roi:+.0%})"
            )
        lines.append("")

    # 归零 / 最差 Call
    dead_calls = [c for c in worst if c["roi"] is not None and c["roi"] <= -0.9]
    if dead_calls:
        lines.append("💀 **归零 Call**")
        for c in dead_calls:
            handle = c["user_handle"]
            snap = c.get("discovery_snapshot") or {}
            symbol = snap.get("symbol", "?")
            chain = snap.get("chain", "?")
            d_mcap = c.get("discovery_mcap")
            c_mcap = c.get("current_mcap")
            roi = c["roi"]

            d_str = format_number(d_mcap) if d_mcap else "?"
            c_str = format_number(c_mcap) if c_mcap else "?"

            lines.append(
                f"  @{handle}: ${symbol} ({chain}) — "
                f"发现时 MC {d_str} → 现在 {c_str} ({roi:+.0%})"
            )
        lines.append("")

    # 潜在优质信号源（被引用的非 List 成员）
    # 从 quoted_handle / retweeted_handle 中寻找被多人引用的外部账号
    external_mentions = defaultdict(set)  # external_handle -> set of list_member_handles
    list_members = {h for h, _ in ranking}
    for c in calls:
        # 检查推文文本中的 @mentions
        snippet = c.get("text_snippet", "")
        import re
        mentioned = re.findall(r'@(\w+)', snippet)
        caller = c["user_handle"]
        for m in mentioned:
            if m.lower() not in {h.lower() for h in list_members}:
                external_mentions[m].add(caller)

    notable_externals = [
        (handle, callers)
        for handle, callers in external_mentions.items()
        if len(callers) >= 2
    ]
    notable_externals.sort(key=lambda x: -len(x[1]))

    if notable_externals:
        lines.append("💡 **潜在优质信号源**（非 List 成员，被多人引用）")
        for handle, callers in notable_externals[:5]:
            callers_str = ", ".join(f"@{c}" for c in sorted(callers))
            lines.append(f"  @{handle} — 被 {callers_str} 引用")
        lines.append("")

    return "\n".join(lines)


def main():
    print("=" * 60)
    print("📊 Alpha Tracker - 周度分析")
    print("=" * 60)

    calls = load_alpha_calls()
    if not calls:
        report = (
            "📊 **Alpha Tracker 周报** | "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n\n"
            "_暂无 alpha call 数据。等待 list_scraper.py 收集含合约地址的推文。_"
        )
        print(report)
        print("\n--- ALPHA_REPORT ---")
        print(report)
        print("--- END ---")
        return

    print(f"📥 加载 {len(calls)} 条 alpha call 记录")

    result = analyze_calls(calls)
    report = generate_report(result)

    print(f"\n📝 报告生成完成")
    print(f"  用户数: {len(result['user_ranking'])}")
    print(f"  有价格数据: {sum(1 for c in result['calls_with_roi'] if c['roi'] is not None)}")

    # 输出报告（供 cron agent 发送到 Discord）
    print("\n--- ALPHA_REPORT ---")
    print(report)
    print("--- END ---")


if __name__ == "__main__":
    main()
