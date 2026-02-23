#!/usr/bin/env python3
"""
dex_utils.py - DexScreener 查询工具共享模块
供 hourly_summary.py / list_scraper.py / alpha_tracker.py 共用
"""

import requests

# DexScreener 缓存（同一进程内避免重复查询）
_dex_cache = {}


def lookup_dexscreener(address: str) -> dict | None:
    """通过 DexScreener API 查询合约地址的链/代币/市值/流动性信息

    Returns:
        dict with keys: chain, dex, symbol, name, price_usd, liquidity_usd,
                        volume_24h, market_cap, url, pair_count
        or None if not found
    """
    address = address.lower()
    if address in _dex_cache:
        return _dex_cache[address]

    try:
        r = requests.get(
            f"https://api.dexscreener.com/latest/dex/tokens/{address}",
            timeout=8,
        )
        data = r.json()
        pairs = data.get("pairs") or []
        if not pairs:
            _dex_cache[address] = None
            return None

        # 选流动性最高的交易对
        best = max(pairs, key=lambda p: (p.get("liquidity") or {}).get("usd") or 0)
        info = {
            "chain": best.get("chainId", "?"),
            "dex": best.get("dexId", "?"),
            "symbol": (best.get("baseToken") or {}).get("symbol", "?"),
            "name": (best.get("baseToken") or {}).get("name", ""),
            "price_usd": best.get("priceUsd"),
            "liquidity_usd": (best.get("liquidity") or {}).get("usd"),
            "volume_24h": (best.get("volume") or {}).get("h24"),
            "market_cap": best.get("marketCap"),
            "url": best.get("url", ""),
            "pair_count": len(pairs),
        }
        _dex_cache[address] = info
        return info
    except Exception:
        _dex_cache[address] = None
        return None


def format_number(n: float | int | None) -> str:
    """格式化数字：1234567 → $1.2M, 56789 → $56.8K"""
    if n is None:
        return "N/A"
    if n >= 1_000_000:
        return f"${n / 1_000_000:.1f}M"
    elif n >= 1_000:
        return f"${n / 1_000:.0f}K"
    else:
        return f"${n:.0f}"


def format_dex_info(address: str) -> str:
    """格式化 DexScreener 查询结果为一行文字"""
    info = lookup_dexscreener(address)
    if not info:
        return f"`{address[:10]}...{address[-6:]}` (未上 DEX)"

    parts = [f"**${info['symbol']}**"]
    parts.append(f"链:{info['chain']}")

    if info.get("price_usd"):
        parts.append(f"价格:${info['price_usd']}")

    mc = info.get("market_cap")
    if mc:
        parts.append(f"MC:{format_number(mc)}")

    liq = info.get("liquidity_usd")
    if liq:
        parts.append(f"流动性:{format_number(liq)}")

    vol = info.get("volume_24h")
    if vol and vol > 0:
        parts.append(f"24h量:{format_number(vol)}")

    if info.get("url"):
        parts.append(f"[DexScreener]({info['url']})")

    return " | ".join(parts)
