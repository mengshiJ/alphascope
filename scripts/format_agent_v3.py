#!/usr/bin/env python3
"""
MA-Format Agent v3 - 投资机会聚焦
输出：中文区 + 英文区 两个版本
"""

import json
import re
from pathlib import Path
from datetime import datetime

INPUT_PATH = "/tmp/filter_output.json"

# 用户画像
USER_PROFILES = {
    # 中文 KOL
    "林迅": {"type": "trading", "name": "林迅", "lang": "zh"},
    "lanaaielsa": {"type": "trading", "name": "lana", "lang": "zh"},
    "PepeBoost888": {"type": "community", "name": "PepeBoost", "lang": "zh"},
    "BTCdayu": {"type": "analysis", "name": "BTCdayu", "lang": "zh"},
    "0xcryptowizard": {"type": "education", "name": "0xWizard", "lang": "zh"},
    "CryptoPainter": {"type": "analysis", "name": "CryptoPainter", "lang": "zh"},
    "ImpossibleSir": {"type": "trading", "name": "林迅", "lang": "zh"},
    "topon1ccc": {"type": "news", "name": "Top1", "lang": "zh"},
    "RicardoPolyGuy": {"type": "trading", "name": "Ricardo阿黄", "lang": "zh"},
    "hazenlee": {"type": "commentary", "name": "HAZENLEE", "lang": "zh"},
    "guoguoX520": {"type": "community", "name": "GUOGUO", "lang": "zh"},
    "0xCryptoWing": {"type": "trading", "name": "Lam", "lang": "zh"},
    "bitcoinzhang1": {"type": "news", "name": "马蹄橘子", "lang": "zh"},
    
    # 英文核心
    "0xAA_Science": {"type": "technical", "name": "0xAA", "lang": "en"},
    "shawmakesmagic": {"type": "technical", "name": "Shaw", "lang": "en"},
    "pmarca": {"type": "official", "name": "Marc Andreessen", "lang": "en"},
    "jessepollak": {"type": "official", "name": "Jesse Pollak", "lang": "en"},
    "cz_binance": {"type": "official", "name": "CZ", "lang": "en"},
    "frankdegods": {"type": "community", "name": "Frank", "lang": "en"},
    "sbf_ftx": {"type": "news", "name": "SBF", "lang": "en"},
    "0xSunNFT": {"type": "alpha", "name": "0xSun", "lang": "en"},
    "AlexanderTw33ts": {"type": "alpha", "name": "Alex", "lang": "en"},
    "StriderOnBase": {"type": "technical", "name": "Strider", "lang": "en"},
    "degenserpent": {"type": "alpha", "name": "DegenSerpent", "lang": "en"},
}


def escape_md(text):
    return text.replace('**', '').replace('__', '').replace('`', '')[:200]


def truncate(text, length=100):
    if len(text) <= length:
        return text
    return text[:length-3] + '...'


def get_user_lang(handle):
    return USER_PROFILES.get(handle, {}).get('lang', 'en')


def format_tweet_alpha(tweet):
    """格式化 Alpha 推文"""
    handle = tweet.get('handle', 'unknown')
    text = tweet.get('text', '')
    alpha_score = tweet.get('alpha_score', 0)
    opp_type = tweet.get('opportunity_type', 'alpha')
    urgency = tweet.get('urgency', 'watch')
    tokens = tweet.get('extracted_tokens', [])
    contracts = tweet.get('extracted_contracts', [])
    url = f"https://x.com/{handle}/status/{tweet.get('tweet_id', '')}" if tweet.get('tweet_id') else ""
    
    profile = USER_PROFILES.get(handle, {})
    name = profile.get('name', handle)
    
    # 紧急度 emoji
    urgency_emoji = {
        'hot': '🔥',
        'warming': '⚡',
        'early': '💡',
        'watch': '👀'
    }.get(urgency, '👀')
    
    # 类型标签
    type_label = {
        'meme_token': '🐸 Meme',
        'new_protocol': '🔧 协议',
        'early_access': '🎁 早期',
        'yield_opportunity': '💰 收益',
        'alpha_signal': '🎯 Alpha'
    }.get(opp_type, '🎯 Alpha')
    
    # 提取的代币
    token_str = ' '.join([f"`${t}`" for t in tokens[:2]]) if tokens else ""
    
    lines = [
        f"{urgency_emoji} **{type_label}** | @{name} | 热度:{int(alpha_score)}",
        f"> {truncate(escape_md(text), 120)}"
    ]
    
    if token_str:
        lines.append(f"🏷️ {token_str}")
    
    if contracts:
        lines.append(f"📄 `{contracts[0][:20]}...` ⚠️验证风险")
    
    lines.append(f"🔗 <{url}>")
    lines.append("")
    
    return '\n'.join(lines)


def generate_reports():
    """生成中英文报告"""
    print("="*60)
    print("🎯 MA-Format Agent v3 | 投资机会聚焦")
    print("="*60)
    
    if not Path(INPUT_PATH).exists():
        print(f"❌ Input file not found: {INPUT_PATH}")
        return None, None
    
    with open(INPUT_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    tweets = data.get('tweets', [])
    new_projects = data.get('new_projects_detected', [])
    
    print(f"📥 Loaded {len(tweets)} alpha tweets")
    print(f"🎯 New projects: {len(new_projects)}")
    
    # 按语言分组
    zh_tweets = [t for t in tweets if get_user_lang(t.get('handle')) == 'zh']
    en_tweets = [t for t in tweets if get_user_lang(t.get('handle')) != 'zh']
    
    # 按 urgency 排序
    for t_list in [zh_tweets, en_tweets]:
        t_list.sort(key=lambda x: {
            'hot': 3, 'warming': 2, 'early': 1, 'watch': 0
        }.get(x.get('urgency'), 0), reverse=True)
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    
    # ========== 中文区报告 ==========
    zh_lines = [
        f"🇨🇳 **中文区监控日报** | {now}",
        "",
        f"📊 **统计**: {len(zh_tweets)} 条投资机会",
        f"🎯 **新发现**: {len([p for p in new_projects if any(t.get('handle') in p.get('sources', []) for t in zh_tweets)])} 个新项目",
        "",
        "─" * 50,
        ""
    ]
    
    # 新项目汇总
    if new_projects:
        zh_lines.append("🚀 **新项目发现**")
        for p in new_projects[:5]:
            sources = ', '.join(p.get('sources', [])[:2])
            zh_lines.append(f"• {p['project']} - {p['mentions']}人提及 by @{sources}")
        zh_lines.append("")
        zh_lines.append("─" * 50)
        zh_lines.append("")
    
    # Hot 机会
    zh_hot = [t for t in zh_tweets if t.get('urgency') == 'hot']
    if zh_hot:
        zh_lines.append("🔥 **Hot 机会** (立即关注)")
        zh_lines.append("")
        for t in zh_hot[:3]:
            zh_lines.append(format_tweet_alpha(t))
    
    # Warming 机会
    zh_warm = [t for t in zh_tweets if t.get('urgency') == 'warming']
    if zh_warm:
        zh_lines.append("⚡ **升温中** (值得关注)")
        zh_lines.append("")
        for t in zh_warm[:5]:
            zh_lines.append(format_tweet_alpha(t))
    
    # Early 信号
    zh_early = [t for t in zh_tweets if t.get('urgency') == 'early']
    if zh_early:
        zh_lines.append("💡 **早期信号** (潜在机会)")
        zh_lines.append("")
        for t in zh_early[:5]:
            zh_lines.append(format_tweet_alpha(t))
    
    zh_lines.append("─" * 50)
    zh_lines.append("💡 数据来自: 20+ 中文 KOL 监控")
    
    zh_report = '\n'.join(zh_lines)
    
    # ========== 英文区报告 ==========
    en_lines = [
        f"🇺🇸 **Global Alpha Digest** | {now}",
        "",
        f"📊 **Stats**: {len(en_tweets)} alpha signals",
        f"🎯 **New Projects**: {len([p for p in new_projects if any(t.get('handle') in p.get('sources', []) for t in en_tweets)])} detected",
        "",
        "─" * 50,
        ""
    ]
    
    # 新项目
    if new_projects:
        en_lines.append("🚀 **New Project Alpha**")
        en_lines.append("_Early mentions with growing traction_")
        en_lines.append("")
        for p in new_projects[:5]:
            sources = ', '.join([f"@{s}" for s in p.get('sources', [])[:2]])
            en_lines.append(f"**{p['project']}**")
            en_lines.append(f"• Mentions: {p['mentions']} | Max Score: {p['max_score']}")
            en_lines.append(f"• Sources: {sources}")
            en_lines.append("")
        en_lines.append("─" * 50)
        en_lines.append("")
    
    # Hot signals
    en_hot = [t for t in en_tweets if t.get('urgency') == 'hot']
    if en_hot:
        en_lines.append("🔥 **Hot Signals** (Act Fast)")
        en_lines.append("")
        for t in en_hot[:3]:
            en_lines.append(format_tweet_alpha(t))
    
    # Warming
    en_warm = [t for t in en_tweets if t.get('urgency') == 'warming']
    if en_warm:
        en_lines.append("⚡ **Warming Up** (Building Momentum)")
        en_lines.append("")
        for t in en_warm[:5]:
            en_lines.append(format_tweet_alpha(t))
    
    # Early
    en_early = [t for t in en_tweets if t.get('urgency') == 'early']
    if en_early:
        en_lines.append("💡 **Early Alpha** (Potential Gems)")
        en_lines.append("")
        for t in en_early[:5]:
            en_lines.append(format_tweet_alpha(t))
    
    en_lines.append("─" * 50)
    en_lines.append("⚡ Sources: Core devs, Founders, Alpha hunters")
    
    en_report = '\n'.join(en_lines)
    
    print(f"\n✅ Format Complete!")
    print(f"   中文区: {len(zh_tweets)} tweets")
    print(f"   英文区: {len(en_tweets)} tweets")
    print("="*60)
    
    return zh_report, en_report


def send_to_discord(content, target_id, label):
    """发送报告到 Discord"""
    import subprocess
    try:
        result = subprocess.run(
            ['openclaw', 'message', 'send', '--channel', 'discord', 
             '--target', target_id, '--message', content],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            print(f"📤 Sent {label} to Discord")
            return True
        else:
            print(f"⚠️ Failed to send {label}: {result.stderr}")
            return False
    except Exception as e:
        print(f"⚠️ Error sending {label}: {e}")
        return False


if __name__ == '__main__':
    zh_report, en_report = generate_reports()
    
    if zh_report and en_report:
        # 保存文件
        with open('/tmp/digest_zh.md', 'w', encoding='utf-8') as f:
            f.write(zh_report)
        with open('/tmp/digest_en.md', 'w', encoding='utf-8') as f:
            f.write(en_report)
        
        print("\n📁 Saved:")
        print("   /tmp/digest_zh.md - 中文区")
        print("   /tmp/digest_en.md - 英文区")
        
        # 发送到 Discord
        print("\n📤 Sending to Discord...")
        send_to_discord(zh_report, "1472806948398436575", "中文区日报")
        send_to_discord(en_report, "1472806948398436575", "英文区日报")
        
        print("\n✅ All tasks complete!")