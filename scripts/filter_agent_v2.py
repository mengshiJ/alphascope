#!/usr/bin/env python3
"""
MA-Filter Agent v2 - 专注于新项目/投资机会发现
"""

import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

INPUT_PATH = "/tmp/scout_output.json"
OUTPUT_PATH = "/tmp/filter_output.json"

# 已知大项目（降低优先级，因为不是新机会）
KNOWN_BIG_PROJECTS = {
    'btc', 'bitcoin', 'eth', 'ethereum', 'sol', 'solana',
    'base', 'arb', 'arbitrum', 'op', 'optimism',
    'bnb', 'binance', 'polygon', 'matic', 'avalanche', 'avax'
}

# 投资机会关键词
ALPHA_KEYWORDS = [
    'launch', ' announcing', ' new token', ' fair launch',
    'presale', 'whitelist', 'airdrop', 'mining', 'yield',
    'contract', 'deployed', 'verified', 'liquidity',
    'early', 'alpha', 'gem', 'opportunity', 'momentum'
]


def extract_tokens(text):
    """提取代币符号"""
    # $XXX 格式
    tokens = re.findall(r'\$([A-Z][A-Z0-9]{1,15})', text)
    return [t for t in tokens if t.lower() not in KNOWN_BIG_PROJECTS]


def extract_contracts(text):
    """提取合约地址"""
    # ETH/Base/BSC 地址
    eth_pattern = r'0x[a-fA-F0-9]{40}'
    # Solana 地址
    sol_pattern = r'[1-9A-HJ-NP-Za-km-z]{32,44}'
    
    contracts = []
    contracts.extend(re.findall(eth_pattern, text))
    contracts.extend([c for c in re.findall(sol_pattern, text) if len(c) > 40])
    return contracts[:3]  # 最多3个


def extract_urls(text):
    """提取项目链接"""
    url_pattern = r'https?://[^\s\)\]\>]+'
    urls = re.findall(url_pattern, text)
    # 过滤掉普通图片/twitter链接
    return [u for u in urls if any(x in u for x in ['github', 'docs', 'app', 'website', 'medium', 'mirror'])]


def calculate_alpha_score(tweet):
    """计算 Alpha 分数（新项目发现潜力）"""
    text = tweet.get('text', '').lower()
    score = 0
    reasons = []
    
    # 1. 新代币提及 (+30)
    tokens = extract_tokens(tweet.get('text', ''))
    if tokens:
        score += 30 * len(tokens)
        reasons.append(f"new_token:{','.join(tokens)}")
    
    # 2. 合约地址 (+50)
    contracts = extract_contracts(tweet.get('text', ''))
    if contracts:
        score += 50
        reasons.append(f"contract:{len(contracts)}")
    
    # 3. Alpha 关键词 (+10 each)
    for kw in ALPHA_KEYWORDS:
        if kw in text:
            score += 10
            reasons.append(f"keyword:{kw}")
            break  # 只算一次
    
    # 4. 项目链接 (+15)
    urls = extract_urls(tweet.get('text', ''))
    if urls:
        score += 15
        reasons.append("project_link")
    
    # 5. 互动分数加权 (但权重降低)
    engagement = tweet.get('likes', 0) + tweet.get('retweets', 0) * 2
    if engagement > 100:
        score += 10
    elif engagement > 20:
        score += 5
    
    # 6. 时间奖励（越新分数越高）
    created_at = tweet.get('created_at', '')
    if created_at:
        try:
            tweet_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            hours_old = (datetime.now(tweet_time.tzinfo) - tweet_time).total_seconds() / 3600
            if hours_old < 2:
                score += 20  # 2小时内额外加分
            elif hours_old < 6:
                score += 10
        except:
            pass
    
    return score, reasons


def classify_opportunity(tweet, alpha_score):
    """分类机会类型"""
    text = tweet.get('text', '').lower()
    
    # 检测类型
    if 'meme' in text or re.search(r'\$[A-Z]{2,8}', tweet.get('text', '')):
        opp_type = "meme_token"
    elif any(x in text for x in ['contract', 'deploy', 'verified', 'liquidity']):
        opp_type = "new_protocol"
    elif any(x in text for x in ['airdrop', 'whitelist', 'early']):
        opp_type = "early_access"
    elif any(x in text for x in ['yield', 'staking', 'mining', 'apr']):
        opp_type = "yield_opportunity"
    else:
        opp_type = "alpha_signal"
    
    # 紧急程度
    if alpha_score >= 80:
        urgency = "hot"  # 热门新机会
    elif alpha_score >= 50:
        urgency = "warming"  # 升温中
    elif alpha_score >= 20:
        urgency = "early"  # 早期信号
    else:
        urgency = "watch"  # 观察
    
    return opp_type, urgency


def detect_new_projects(tweets):
    """检测新项目（首次提及）"""
    project_mentions = defaultdict(list)
    
    for t in tweets:
        text = t.get('text', '')
        # 提取所有潜在项目标识
        tokens = extract_tokens(text)
        for token in tokens:
            project_mentions[token].append({
                'handle': t.get('handle'),
                'score': t.get('alpha_score', 0),
                'time': t.get('created_at')
            })
    
    # 找提及次数少但互动不错的（新信号）
    new_signals = []
    for project, mentions in project_mentions.items():
        if len(mentions) <= 3:  # 不超过3人提及（新）
            max_score = max(m['score'] for m in mentions)
            if max_score >= 30:  # 有一定质量
                new_signals.append({
                    'project': f"${project}",
                    'mentions': len(mentions),
                    'max_score': max_score,
                    'sources': [m['handle'] for m in mentions]
                })
    
    return sorted(new_signals, key=lambda x: x['max_score'], reverse=True)[:10]


def filter_tweets():
    """主过滤函数"""
    print("="*60)
    print("🔍 MA-Filter Agent v2 | Alpha Hunter Mode")
    print("="*60)
    
    # 读取 Scout 输出
    if not Path(INPUT_PATH).exists():
        print(f"❌ Input file not found: {INPUT_PATH}")
        return False
    
    with open(INPUT_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    tweets = data.get('tweets', [])
    print(f"📥 Loaded {len(tweets)} tweets from Scout")
    
    filtered = []
    
    for tweet in tweets:
        # 计算 Alpha 分数
        alpha_score, reasons = calculate_alpha_score(tweet)
        
        # 过滤阈值：Alpha 分数 >= 20（新项目信号）
        if alpha_score >= 20:
            opp_type, urgency = classify_opportunity(tweet, alpha_score)
            
            # 提取关键信息
            tokens = extract_tokens(tweet.get('text', ''))
            contracts = extract_contracts(tweet.get('text', ''))
            urls = extract_urls(tweet.get('text', ''))
            
            filtered.append({
                **tweet,
                'alpha_score': alpha_score,
                'alpha_reasons': reasons,
                'opportunity_type': opp_type,
                'urgency': urgency,
                'extracted_tokens': tokens,
                'extracted_contracts': contracts,
                'extracted_urls': urls
            })
    
    # 去重
    seen_ids = set()
    unique_filtered = []
    for t in filtered:
        tid = t.get('tweet_id')
        if tid and tid not in seen_ids:
            seen_ids.add(tid)
            unique_filtered.append(t)
        elif not tid:
            unique_filtered.append(t)
    
    # 按 Alpha 分数排序
    unique_filtered.sort(key=lambda x: x['alpha_score'], reverse=True)
    
    # 检测新项目
    new_projects = detect_new_projects(unique_filtered)
    
    # 分类统计
    type_stats = defaultdict(int)
    urgency_stats = defaultdict(int)
    for t in unique_filtered:
        type_stats[t['opportunity_type']] += 1
        urgency_stats[t['urgency']] += 1
    
    # 保存结果
    output = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "input_count": len(tweets),
        "filtered_count": len(unique_filtered),
        "new_projects_detected": new_projects,
        "type_breakdown": dict(type_stats),
        "urgency_breakdown": dict(urgency_stats),
        "tweets": unique_filtered
    }
    
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n📊 Filter Summary:")
    print(f"   Input: {len(tweets)} tweets")
    print(f"   Alpha signals: {len(unique_filtered)} tweets")
    print(f"   New projects: {len(new_projects)}")
    print(f"   Types: Meme={type_stats['meme_token']}, Protocol={type_stats['new_protocol']}, Early={type_stats['early_access']}")
    print(f"   Urgency: Hot={urgency_stats['hot']}, Warming={urgency_stats['warming']}, Early={urgency_stats['early']}")
    
    if new_projects:
        print(f"\n🎯 Top New Signals:")
        for p in new_projects[:5]:
            print(f"   {p['project']} - {p['mentions']} mentions, score {p['max_score']}")
    
    print(f"\n✅ Filter Complete!")
    print("="*60)
    
    return len(unique_filtered) > 0


if __name__ == '__main__':
    import sys
    success = filter_tweets()
    sys.exit(0 if success else 1)