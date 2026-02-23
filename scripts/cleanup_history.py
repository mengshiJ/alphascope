#!/usr/bin/env python3
"""
清理 X-Monitor 历史文件
- history/*.jsonl: 保留最近 3 天
- alpha_calls.jsonl: 保留最近 30 天的记录
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# 配置
DATA_DIR = Path(__file__).parent.parent / "data"
HISTORY_DIR = DATA_DIR / "history"
ALPHA_CALLS_PATH = DATA_DIR / "alpha_calls.jsonl"

KEEP_DAYS = 3           # history 保留天数
ALPHA_KEEP_DAYS = 30    # alpha_calls 保留天数


def cleanup_old_files(keep_days: int = KEEP_DAYS):
    """删除超过 keep_days 天的历史文件"""
    if not HISTORY_DIR.exists():
        print(f"❌ 历史目录不存在: {HISTORY_DIR}")
        return

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=keep_days)
    deleted_count = 0
    total_size = 0

    for file in HISTORY_DIR.glob("*.jsonl"):
        # 从文件名提取日期 (格式: YYYY-MM-DD.jsonl)
        try:
            date_str = file.stem  # e.g., "2026-02-18"
            file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)

            if file_date < cutoff_date:
                size = file.stat().st_size
                total_size += size
                file.unlink()
                deleted_count += 1
                print(f"🗑️  删除: {file.name} ({size / 1024:.1f} KB)")

        except (ValueError, OSError) as e:
            print(f"⚠️  跳过文件 {file.name}: {e}")

    if deleted_count > 0:
        print(f"\n✅ History 清理完成：删除 {deleted_count} 个文件，释放 {total_size / 1024:.1f} KB")
    else:
        print(f"✅ History 无需清理：所有文件都在保留期内（{keep_days}天）")


def cleanup_alpha_calls(keep_days: int = ALPHA_KEEP_DAYS):
    """清理 alpha_calls.jsonl 中超过 keep_days 天的记录"""
    if not ALPHA_CALLS_PATH.exists():
        print(f"✅ Alpha calls 文件不存在，跳过")
        return

    cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat()
    kept = []
    removed = 0

    with open(ALPHA_CALLS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                discovered_at = rec.get("discovered_at", "")
                if discovered_at >= cutoff:
                    kept.append(line)
                else:
                    removed += 1
            except json.JSONDecodeError:
                continue

    if removed > 0:
        with open(ALPHA_CALLS_PATH, "w", encoding="utf-8") as f:
            for line in kept:
                f.write(line + "\n")
        print(f"✅ Alpha calls 清理完成：删除 {removed} 条记录，保留 {len(kept)} 条（{keep_days}天）")
    else:
        print(f"✅ Alpha calls 无需清理：{len(kept)} 条记录都在保留期内（{keep_days}天）")


if __name__ == "__main__":
    keep = int(sys.argv[1]) if len(sys.argv) > 1 else KEEP_DAYS
    print(f"🧹 开始清理 X-Monitor 数据...")
    print(f"  History: 超过 {keep} 天的文件")
    print(f"  Alpha calls: 超过 {ALPHA_KEEP_DAYS} 天的记录")
    print()
    cleanup_old_files(keep)
    print()
    cleanup_alpha_calls()
