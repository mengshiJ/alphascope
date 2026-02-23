#!/usr/bin/env python3
"""
X Cookie Browser - 以正文为核心，评论区为辅
带 API Fallback 支持
"""

import asyncio
import json
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, Any, List

try:
    from playwright.async_api import async_playwright, Page, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("Warning: playwright not installed, will use API mode only")


class XAPIFallback:
    """使用 FxEmbed API 作为浏览器抓取失败时的 fallback."""
    
    API_BASE = "https://api.fxtwitter.com"
    
    @staticmethod
    def extract_tweet_id(url: str) -> Optional[str]:
        """从 URL 中提取推文 ID."""
        # 支持格式:
        # https://x.com/username/status/123456...
        # https://twitter.com/username/status/123456...
        import re
        match = re.search(r'(?:twitter\.com|x\.com)/\w+/status/(\d+)', url)
        return match.group(1) if match else None
    
    def fetch_via_api(self, url: str) -> Optional[Dict[str, Any]]:
        """
        使用 FxEmbed API 抓取推文.
        
        Returns:
            统一格式的结果字典，与浏览器版本兼容
        """
        tweet_id = self.extract_tweet_id(url)
        if not tweet_id:
            print("❌ 无法从 URL 中提取推文 ID")
            return None
        
        api_url = f"{self.API_BASE}/status/{tweet_id}"
        
        try:
            print(f"🔌 使用 API 抓取: {api_url}")
            
            req = urllib.request.Request(
                api_url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
            
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            if data.get('code') != 200 or not data.get('tweet'):
                print(f"❌ API 返回错误: {data.get('message', 'Unknown error')}")
                return None
            
            tweet = data['tweet']
            
            # 转换为统一格式
            result = {
                "main": {
                    "author": tweet.get('author', {}).get('name', ''),
                    "handle": f"@{tweet.get('author', {}).get('screen_name', '')}",
                    "time": tweet.get('created_at', ''),
                    "text": tweet.get('text', ''),
                    "stats": {
                        "replies": tweet.get('replies', 0),
                        "retweets": tweet.get('retweets', 0),
                        "likes": tweet.get('likes', 0),
                        "views": str(tweet.get('views', ''))
                    },
                    "media": []
                },
                "comments": [],
                "source": "api"  # 标记数据来源
            }
            
            # 处理媒体
            media = tweet.get('media', {}).get('all', [])
            for m in media:
                if m.get('type') == 'photo':
                    result["main"]["media"].append(m.get('url', ''))
                elif m.get('type') in ['video', 'gif']:
                    result["main"]["media"].append('video')
            
            print(f"✅ API 抓取成功")
            print(f"   作者: {result['main']['author']} {result['main']['handle']}")
            print(f"   内容: {result['main']['text'][:100]}...")
            
            return result
            
        except urllib.error.HTTPError as e:
            print(f"❌ API HTTP 错误: {e.code} - {e.reason}")
            return None
        except Exception as e:
            print(f"❌ API 请求失败: {e}")
            return None


class XCookieBrowser:
    """Browser automation for X/Twitter using cookie authentication."""
    
    def __init__(self, cookies_path: str = "~/.openclaw/workspace/.secrets/x_cookies.json"):
        self.cookies_path = Path(cookies_path).expanduser()
        self.cookies: Dict[str, str] = {}
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.api_fallback = XAPIFallback()
        
    def load_cookies(self) -> bool:
        """Load cookies from JSON file."""
        if not self.cookies_path.exists():
            print(f"⚠️  Cookies file not found: {self.cookies_path}")
            return False
            
        try:
            with open(self.cookies_path) as f:
                self.cookies = json.load(f)
            return True
        except Exception as e:
            print(f"❌ Failed to load cookies: {e}")
            return False
    
    async def init_browser(self, headless: bool = True):
        """Initialize browser with cookies."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright not installed")
            
        playwright = await async_playwright().start()
        
        self.browser = await playwright.chromium.launch(
            headless=headless,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        
        # Add cookies
        if self.cookies.get('auth_token'):
            await self.context.add_cookies([
                {'name': 'auth_token', 'value': self.cookies['auth_token'], 'domain': '.x.com', 'path': '/'},
                {'name': 'ct0', 'value': self.cookies.get('ct0', ''), 'domain': '.x.com', 'path': '/'},
                {'name': 'twid', 'value': self.cookies.get('twid', ''), 'domain': '.x.com', 'path': '/'},
            ])
        
        self.page = await self.context.new_page()
    
    async def fetch_tweet(self, url: str, include_comments: bool = False, wait: int = 5, use_fallback: bool = True) -> Dict[str, Any]:
        """
        抓取推文 - 以正文为核心，评论区为辅
        
        策略:
        1. 优先使用浏览器方式（功能完整）
        2. 如果失败且允许 fallback，使用 API 方式
        
        Returns:
            {
                "main": {...},
                "comments": [...],
                "source": "browser" | "api"
            }
        """
        # 尝试浏览器方式
        browser_result = None
        if PLAYWRIGHT_AVAILABLE and self.cookies.get('auth_token'):
            try:
                browser_result = await self._fetch_via_browser(url, include_comments, wait)
                if browser_result and browser_result.get('main', {}).get('text'):
                    browser_result['source'] = 'browser'
                    return browser_result
            except Exception as e:
                print(f"⚠️  浏览器抓取失败: {e}")
        else:
            print("⚠️  浏览器不可用（playwright 未安装或 cookies 无效）")
        
        # Fallback 到 API
        if use_fallback:
            print("🔄 切换到 API fallback...")
            api_result = self.api_fallback.fetch_via_api(url)
            if api_result:
                return api_result
        
        # 都失败了，返回浏览器尝试的结果（如果有）或空结果
        return browser_result or {"main": {}, "comments": [], "source": "failed"}
    
    async def _fetch_via_browser(self, url: str, include_comments: bool = False, wait: int = 5) -> Dict[str, Any]:
        """内部方法：通过浏览器抓取."""
        if not self.page:
            await self.init_browser(headless=True)
        
        print(f"🐦 浏览器抓取: {url}")
        await self.page.goto(url, wait_until="networkidle", timeout=90000)
        await asyncio.sleep(wait)
        
        result = {"main": {}, "comments": []}
        
        # === 1. 抓取正文（核心）===
        main_tweet = await self.page.evaluate('''() => {
            const data = {
                author: "",
                handle: "",
                time: "",
                text: "",
                stats: {replies: 0, retweets: 0, likes: 0, views: ""},
                media: []
            };
            
            // 找到主推文（第一个 article）
            const article = document.querySelector('article[data-testid="tweet"]');
            if (!article) return data;
            
            // 作者信息
            const nameEl = article.querySelector('[data-testid="User-Name"]');
            if (nameEl) {
                const links = nameEl.querySelectorAll('a');
                if (links[0]) data.author = links[0].innerText;
                if (links[1]) data.handle = links[1].innerText;
            }
            
            // 发布时间
            const timeEl = article.querySelector('time');
            if (timeEl) {
                data.time = timeEl.getAttribute('datetime');
            }
            
            // 正文内容 - 多种尝试
            const textSelectors = [
                '[data-testid="tweetText"]',
                'div[dir="auto"][lang]'
            ];
            
            for (const sel of textSelectors) {
                const el = article.querySelector(sel);
                if (el && el.innerText.length > 10) {
                    data.text = el.innerText;
                    break;
                }
            }
            
            // 如果没找到，尝试获取 article 内所有文本
            if (!data.text) {
                const allText = [];
                article.querySelectorAll('div[dir="auto"]').forEach(el => {
                    if (el.innerText.length > 5) allText.push(el.innerText);
                });
                // 过滤掉作者名和 handle
                data.text = allText.find(t => t.length > 20 && !t.includes('@')) || "";
            }
            
            // 互动数据
            const getStat = (testid) => {
                const el = article.querySelector(`[data-testid="${testid}"]`);
                if (el) {
                    const text = el.innerText || el.getAttribute('aria-label') || "";
                    const match = text.match(/[\d,]+/);
                    return match ? parseInt(match[0].replace(',', '')) : 0;
                }
                return 0;
            };
            
            data.stats.replies = getStat('reply');
            data.stats.retweets = getStat('retweet');
            data.stats.likes = getStat('like');
            
            // 浏览量
            const viewEl = article.querySelector('a[href*="analytics"] span');
            if (viewEl) {
                data.stats.views = viewEl.innerText;
            }
            
            // 媒体检测
            article.querySelectorAll('img[src*="twimg.com"]').forEach(img => {
                if (!img.src.includes('profile')) {
                    data.media.push(img.src);
                }
            });
            if (article.querySelector('video')) {
                data.media.push("video");
            }
            
            return data;
        }''')
        
        result["main"] = main_tweet
        
        print(f"✅ 正文已抓取")
        print(f"   作者: {main_tweet.get('author', 'N/A')} {main_tweet.get('handle', '')}")
        print(f"   内容: {main_tweet.get('text', '')[:100]}...")
        print(f"   媒体: {len(main_tweet.get('media', []))} 个")
        
        # === 2. 抓取评论（辅助）===
        if include_comments:
            print("💬 正在抓取评论...")
            
            # 滚动加载更多评论
            for _ in range(3):
                await self.page.evaluate('window.scrollBy(0, 800)')
                await asyncio.sleep(2)
            
            comments = await self.page.evaluate('''() => {
                const comments = [];
                const articles = document.querySelectorAll('article[data-testid="tweet"]');
                
                // 跳过第一个（主推文）
                for (let i = 1; i < Math.min(articles.length, 15); i++) {
                    const article = articles[i];
                    
                    const authorEl = article.querySelector('[data-testid="User-Name"]');
                    const textEl = article.querySelector('[data-testid="tweetText"]');
                    const timeEl = article.querySelector('time');
                    
                    if (textEl) {
                        comments.push({
                            author: authorEl ? authorEl.innerText.split('\\n')[0] : 'Unknown',
                            text: textEl.innerText,
                            time: timeEl ? timeEl.getAttribute('datetime') : null
                        });
                    }
                }
                
                return comments;
            }''')
            
            result["comments"] = comments
            print(f"✅ 评论已抓取: {len(comments)} 条")
        
        return result
    
    async def screenshot(self, url: str, output: str = "screenshot.png", wait: int = 5):
        """Take a screenshot of a page (browser only)."""
        if not self.page:
            raise RuntimeError("Browser not initialized")
            
        await self.page.goto(url, wait_until="networkidle", timeout=90000)
        await asyncio.sleep(wait)
        await self.page.screenshot(path=output, full_page=True)
        print(f"💾 截图已保存: {output}")
    
    async def close(self):
        """Close browser and cleanup."""
        if self.browser:
            await self.browser.close()


async def main():
    parser = argparse.ArgumentParser(description='X Cookie Browser - 以正文为核心，带 API Fallback')
    parser.add_argument('--cookies', '-c', 
                       default='~/.openclaw/workspace/.secrets/x_cookies.json')
    parser.add_argument('--tweet-url', '-t', required=True, help='推文 URL')
    parser.add_argument('--comments', action='store_true', help='包含评论（仅浏览器模式）')
    parser.add_argument('--output', '-o', help='输出 JSON 文件')
    parser.add_argument('--wait', '-w', type=int, default=5, help='等待时间')
    parser.add_argument('--screenshot', '-s', help='同时截图保存路径')
    parser.add_argument('--api-only', action='store_true', help='仅使用 API 模式（快速）')
    parser.add_argument('--no-fallback', action='store_true', help='禁用 API fallback')
    
    args = parser.parse_args()
    
    browser = XCookieBrowser(cookies_path=args.cookies)
    
    # API-only 模式
    if args.api_only:
        print("🔌 API-only 模式")
        api_fetcher = XAPIFallback()
        result = api_fetcher.fetch_via_api(args.tweet_url)
    else:
        # 正常模式：浏览器为主，API 为 fallback
        cookies_loaded = browser.load_cookies()
        
        if not cookies_loaded and args.no_fallback:
            print("❌ 无 cookies 且禁用 fallback，无法继续")
            return
        
        try:
            result = await browser.fetch_tweet(
                args.tweet_url, 
                include_comments=args.comments,
                wait=args.wait,
                use_fallback=not args.no_fallback
            )
        finally:
            await browser.close()
    
    if not result:
        print("❌ 抓取失败")
        return
    
    # 输出到文件或 stdout
    output_json = json.dumps(result, ensure_ascii=False, indent=2)
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output_json)
        print(f"💾 结果已保存: {args.output}")
    else:
        print("\n" + "="*60)
        print(output_json)
    
    # 显示数据来源
    source = result.get('source', 'unknown')
    print(f"\n📊 数据来源: {source}")
    
    # 可选截图（仅浏览器模式）
    if args.screenshot and not args.api_only and source == 'browser':
        await browser.init_browser(headless=True)
        try:
            await browser.screenshot(args.tweet_url, args.screenshot, wait=args.wait)
        finally:
            await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
