---
name: x-cookie-browser
description: Access X/Twitter content using browser automation with cookie authentication. Designed with "main tweet content as core, comments as supplementary" workflow. Supports regular tweets, X Articles, and comment extraction. Now includes API fallback for reliability.
---

# X Cookie Browser 🍪🐦

Access X/Twitter content using **browser automation** with **API fallback** for maximum reliability.

**设计原则：以正文为核心，评论区为辅**
**架构原则：浏览器为主，API 为 fallback**

---

## Architecture

```
┌─────────────────────────────────────────┐
│          X Cookie Browser               │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │  第1层：Browser (Primary)        │   │
│  │  - 功能完整（评论、截图）          │   │
│  │  - 需要 cookies                   │   │
│  │  - 较慢但完整                      │   │
│  └─────────────────────────────────┘   │
│              ↓ 失败时自动切换             │
│  ┌─────────────────────────────────┐   │
│  │  第2层：API Fallback             │   │
│  │  - FxEmbed API (无需 cookies)    │   │
│  │  - 快速但功能简化                  │   │
│  │  - 支持正文 + 元数据               │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

---

## Prerequisites

```bash
pip install playwright
playwright install chromium
```

**Optional - Cookies file**: `~/.openclaw/workspace/.secrets/x_cookies.json`
```json
{
  "auth_token": "your_auth_token",
  "ct0": "your_ct0_token", 
  "twid": "u%3Dyour_user_id"
}
```

> 💡 没有 cookies？没关系！API fallback 无需登录即可工作。

---

## Quick Start

### 默认模式：浏览器为主，API 为 fallback

```bash
python3 scripts/x_fetch.py --tweet-url "https://x.com/yanakz3/status/..."
```

**自动切换逻辑：**
1. 先尝试浏览器方式（需要 cookies）
2. 如果失败（无 cookies / 超时 / 被封），自动使用 API

### API-only 模式（最快）

```bash
python3 scripts/x_fetch.py --tweet-url "URL" --api-only
```

### 纯浏览器模式（禁用 fallback）

```bash
python3 scripts/x_fetch.py --tweet-url "URL" --no-fallback
```

### 抓取推文 + 评论（仅浏览器支持）

```bash
python3 scripts/x_fetch.py \
  --tweet-url "https://x.com/yanakz3/status/..." \
  --comments
```

---

## Output Format

```json
{
  "main": {
    "author": "BitCow",
    "handle": "@Yanakz3", 
    "time": "2026-02-04T14:59:00.000Z",
    "text": "你本来可以慢慢变富——为什么我希望你卸掉杠杠...",
    "stats": {"replies": 9, "retweets": 55, "likes": 216, "views": "54K"},
    "media": ["img1.jpg", "video"]
  },
  "comments": [],
  "source": "browser"
}
```

**`source` 字段说明：**
- `"browser"` - 浏览器抓取（完整功能）
- `"api"` - API fallback（正文 + 元数据）
- `"failed"` - 两种方法都失败

---

## Python API

```python
from scripts.x_fetch import XCookieBrowser, XAPIFallback

# 方式1：自动 fallback 模式
async def fetch_with_fallback():
    browser = XCookieBrowser()
    browser.load_cookies()  # 可选：没有 cookies 会 fallback 到 API
    
    result = await browser.fetch_tweet(
        "https://x.com/yanakz3/status/...",
        include_comments=True,
        use_fallback=True  # 启用 API fallback
    )
    
    print(f"数据来源: {result['source']}")
    print(f"标题: {result['main']['text'][:50]}...")
    
    await browser.close()

# 方式2：纯 API 模式（最快，无需 cookies）
def fetch_via_api_only():
    api = XAPIFallback()
    result = api.fetch_via_api("https://x.com/...")
    
    if result:
        print(result['main']['text'])
```

---

## Feature Comparison

| 功能 | Browser | API Fallback |
|:---|:---:|:---:|
| 正文抓取 | ✅ | ✅ |
| 作者信息 | ✅ | ✅ |
| 互动数据（转评赞） | ✅ | ✅ |
| 媒体检测 | ✅ | ✅ |
| 评论抓取 | ✅ | ❌ |
| 截图功能 | ✅ | ❌ |
| 需要 cookies | ✅ | ❌ |
| 速度 | 🐢 慢 | ⚡ 快 |
| 稳定性 | 可能被封 | 稳定 |

---

## CLI 选项

```
python3 scripts/x_fetch.py --help

Options:
  -t, --tweet-url URL     推文 URL (必需)
  -c, --cookies PATH      Cookies 文件路径
  --comments              抓取评论 (仅浏览器)
  -o, --output FILE       输出 JSON 文件
  -w, --wait SECONDS      等待时间 (默认: 5)
  -s, --screenshot FILE   截图保存路径 (仅浏览器)
  --api-only              仅使用 API 模式
  --no-fallback          禁用 API fallback
```

---

## Use Cases

### 场景1：快速获取正文（推荐 API-only）
```bash
python3 scripts/x_fetch.py -t "URL" --api-only | jq '.main.text'
```

### 场景2：完整分析（需要评论）
```bash
python3 scripts/x_fetch.py -t "URL" --comments -o analysis.json
```

### 场景3：批量监控（自动 fallback）
```python
# 无 cookies 也能工作，自动 fallback 到 API
browser = XCookieBrowser()
for url in tweet_urls:
    result = await browser.fetch_tweet(url, use_fallback=True)
    print(f"[{result['source']}] {result['main']['text'][:50]}")
```

---

## Troubleshooting

**浏览器抓取失败，自动 fallback 到 API？**
- ✅ 这是正常行为，结果仍然有效
- 检查 cookies 是否过期

**正文为空？**
- 增加等待时间：`--wait 10`
- 或切换到 `--api-only` 模式

**需要评论但 API 模式不支持？**
- 必须提供有效的 cookies 使用浏览器模式

**API 也失败了？**
- 检查网络连接
- FxEmbed 服务可能暂时不可用

---

## Credits

- **Browser automation**: Playwright
- **API Fallback**: [FxEmbed](https://github.com/dangeredwolf/fxembed) (免费 Twitter 代理 API)
