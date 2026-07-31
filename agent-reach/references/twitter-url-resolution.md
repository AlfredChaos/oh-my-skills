# Twitter Article URL Resolution & Cross-Platform Fallback

## Twitter `/i/status/` vs `/i/article/` — Two Different ID Systems

| URL pattern | Content type | Auth required | bird | vxtwitter API | Thread Reader |
|-------------|-------------|---------------|------|---------------|---------------|
| `x.com/i/status/<id>` | Regular tweet | Cookie or Bearer | ✅ | ✅ | ✅ (if indexed) |
| `x.com/i/article/<id>` | Twitter Article (long-form, up to 25k chars) | `auth_token` + `ct0` cookie | ✅ (with auth) | ❌ | ✅ (if indexed) |

**Key insight**: `/i/status/` and `/i/article/` use **different ID namespaces**. A tweet ID and an article ID are not interchangeable.

### Observed Resolution Chain

When accessing a tweet via `vxtwitter API`, the response for some tweets contains an `x.com/i/article/<id>` link in the `text` field:

```
vxtwitter response.text → "http://x.com/i/article/2060729909690224640"
```

This does NOT mean the original tweet IS that article — it's a separate piece of content referenced by the tweet.

### Credential Options for Twitter Article Access

1. **Browser cookies** (Safari/Chrome/Firefox, logged into x.com) — detected automatically by `bird`
2. **Environment variables**: `AUTH_TOKEN` + `CT0`
3. **CLI flags**: `--auth-token <token>` / `--ct0 <token>`

To get tokens: in x.com browser DevTools → Application → Cookies → find `auth_token` and `ct0`.

## Cross-Platform Fallback Strategy for Chinese Creator Content

Many Chinese content creators cross-post across:
- **Twitter/X** — often a summary or pointer
- **微信公众号 (WeChat Official Accounts)** — canonical long-form source
- **小红书 / 抖音** — short-form versions

### When All Twitter Methods Fail

1. **Exa search** the tweet's content or subject line to find the WeChat original
2. **WeChat article** → use `wechat-article-for-ai` (Camoufox) to read faithfully
3. The tweet often references the WeChat article in its text, making the WeChat URL findable via search

### Example Pattern (dontbesilent case)

```
Tweet: x.com/i/status/2017963276131598428 (dontbesilent)
  → Contains reference to: https://mp.weixin.qq.com/s/bMzRDMJ0h6wbNbfAx_deNQ
  → WeChat article readable via Camoufox → full content captured
  → Twitter tweet was a recommendation, not the source
```

This pattern applies to most Chinese creator accounts that post long-form content — they typically use Twitter to drive traffic to their WeChat accounts.

## Tool Quick-Reference for Twitter

| Tool | Command | Notes |
|------|---------|-------|
| bird (Agent Reach) | `bird read <url>` | Needs auth cookies or env tokens |
| vxtwitter API | `curl -sL "https://api.vxtwitter.com/<id>"` | Only works for `/i/status/` tweets, not Articles. Basic engagement + media URLs. |
| **fxtwitter API** | `curl -sL "https://api.fxtwitter.com/<id>"` | Richer than vxtwitter: ALL video variants (480p→4K + HLS), current engagement (views/bookmarks/quotes), author metadata. Prefer for media-heavy tweets. |
| **yt-dlp direct** | `yt-dlp -f "worst[ext=mp4]/worst" <url>` | Downloads video WITHOUT cookies (guest token auto-acquired). Bypasses `video.twimg.com` CDN timeout. Best for ASR ingestion. |
| Thread Reader | `curl -sL "https://threadreaderapp.com/thread/<id>.html"` | Indexing lags; only shows if previously submitted |
| Unroll Now | `curl -sL "https://unrollnow.com/status/<id>"` | **No indexing required for single `/status/` pages** — returns tweet text + video CDN URL + thumbnail + timestamp even for brand-new tweets. See HTML parser below |
| Jina Reader | `curl -s "https://r.jina.ai/<url>"` | Times out on x.com; do not rely on this for Twitter |

## fxtwitter API — Richer Than vxtwitter

When `vxtwitter` works but the engagement numbers look stale or you need to
pick a specific video resolution, prefer **fxtwitter**. Same auth-less API
pattern (`https://api.fxtwitter.com/i/status/<id>`) but richer payload:

```json
{
  "code": 200, "message": "OK",
  "tweet": {
    "id": "2080376094939603366",
    "text": "Voice mode now runs on Claude's more capable models...",
    "author": { "screen_name": "claudeai", "followers": 1674365, ... },
    "replies": 649, "retweets": 701, "likes": 10303,
    "bookmarks": 2085, "quotes": 382, "views": 1320875,
    "media": { "all": [{
      "duration": 11.458, "width": 3840, "height": 2160,
      "formats": [
        { "url": ".../vid/avc1/480x270/...mp4", "bitrate": 256000 },
        { "url": ".../vid/avc1/640x360/...mp4", "bitrate": 832000 },
        { "url": ".../vid/avc1/1280x720/...mp4", "bitrate": 2176000 },
        { "url": ".../vid/avc1/1920x1080/...mp4", "bitrate": 10368000 },
        { "url": ".../vid/avc1/3840x2160/...mp4", "bitrate": 25128000 },
        { "url": ".../pl/...m3u8", "container": "m3u8" }
      ]
    }]}
  }
}
```

**Why fxtwitter over vxtwitter**:
- Returns ALL bitrate variants (5 mp4 + 1 HLS playlist) so you can pick the
  smallest for transcription or the largest for archival
- Engagement counts are more current (views/bookmarks/quotes/verified type)
- Includes author metadata (followers, verification, banner URL)

Verified 2026-07-25 on @claudeai's Voice Mode announcement — vxtwitter
returned only the 4K URL and stale engagement; fxtwitter gave 6 variants +
1.32M views / 10.3K likes.

## yt-dlp Direct Download (No Cookies Required)

For video ingestion where you just need the audio for `mlx_whisper`
transcription, **`yt-dlp` itself is the fastest path** — it acquires a guest
token internally and downloads without any Twitter auth:

```bash
# Smallest variant (480p 256 kbps mp4) — ideal for ASR
yt-dlp -f "worst[ext=mp4]/worst" -o "/tmp/voice.%(ext)s" \
  "https://x.com/i/status/<id>"

# Pull only the auto-generated thumbnail (jpg)
yt-dlp --write-thumb --convert-thumb jpg --no-warnings \
  -o "/tmp/thumb.%(ext)s" "https://x.com/i/status/<id>"
```

For an 11.5-second 4K clip, this delivers a ~113 KB 480p mp4 in ~2 seconds.
The 4K original (25 Mbps, ~36 MB) over direct `curl` to
`video.twimg.com/amplify_video/.../*.mp4` times out (exit 28) from this
environment even on a 1 KB probe — yt-dlp's Twitter extractor uses a
working CDN path that bypasses that timeout.

After download, convert + transcribe:

```bash
ffmpeg -i voice.mp4 -vn -ac 1 -ar 16000 -c:a pcm_s16le voice.wav -y
mlx_whisper voice.wav --model mlx-community/whisper-large-v3-turbo \
  --output-format all --output-dir . --output-name voice \
  --language en --temperature 0
```

## Unroll Now Fallback for Single-Tweet Capture

When `bird read` fails (no auth) AND `vxtwitter` returns `{"error":"User not found."}` (occasional
API issue even for live tweets, observed 2026-06-11 on @dontbesilent tweet 2064745433109528904),
`unrollnow.com/status/<id>` is the most reliable single-tweet fallback. It does **not** require
prior indexing like Thread Reader does.

### Verifying availability

```bash
curl -sL "https://unrollnow.com/status/2064745433109528904" -o /tmp/unroll.html
wc -l /tmp/unroll.html
grep -c "article-content" /tmp/unroll.html   # > 0 means tweet body present
```

### HTML structure (single tweet page)

Key DOM markers to extract tweet body + media:

```html
<!-- Tweet text: <p class="article-paragraph tweet-content clickable-tweet"> -->
<p class='article-paragraph tweet-content clickable-tweet' data-tweet-index='1'>
  全球任何一个内容平台，冷启动必过万粉，我的方法论
</p>

<!-- Video CDN URL is in data-video-url (no watermark, no auth needed) -->
<div class="mediadiv video-container">
  <div class="video-player-wrapper"
       data-video-url="https://video.twimg.com/amplify_video/<video_id>/vid/avc1/<WxH>/<file>.mp4?tag=27">
    <img class="video-thumbnail" src="https://pbs.twimg.com/amplify_video_thumb/<video_id>/img/<hash>.jpg">
    <video class="tweet-video" preload="metadata">
      <source src="https://video.twimg.com/.../file.mp4?tag=27" type="video/mp4">
    </video>
  </div>
</div>

<!-- Hidden metadata blocks -->
<div class="tweet-data-hidden"
     data-tweet-index="1"
     data-tweet-time="Jun 10, 2026 • 4:24 PM"
     data-tweet-id="2064745433109528904"></div>
<div id="cleanBodyText" style="display:none;">...cleaned text...</div>
```

### One-shot extraction (Python regex on the curl response)

```python
import re
html = open('/tmp/unroll.html').read()

m = re.search(r"class='article-paragraph tweet-content[^']*'[^>]*>([^<]+)</p>", html)
tweet_text = m.group(1).strip() if m else None

vids = re.findall(r'data-video-url="(https://video\.twimg\.com/amplify_video/[^"]+\.mp4[^"]*)"', html)
thumbs = re.findall(r'<img class="video-thumbnail" src="(https://pbs\.twimg\.com/amplify_video_thumb/[^"]+)"', html)
ts = re.search(r'data-tweet-time="([^"]+)"', html)
tid = re.search(r'data-tweet-id="([^"]+)"', html)
```

### Download the video

Twitter `amplify_video` CDN serves the original with any standard UA — no login, no watermark:

```bash
# 1440x2560 vertical files are typically ~25MB/min, H264/AAC
curl -sL -A "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15" \
  -o /tmp/tweet-<id>.mp4 \
  "https://video.twimg.com/amplify_video/<video_id>/vid/avc1/<WxH>/<file>.mp4?tag=27"

file /tmp/tweet-<id>.mp4
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 /tmp/tweet-<id>.mp4
```

Then extract audio + transcribe with `mlx_whisper` (Apple Silicon) or `whisper` CLI. See the
standard video ingestion path in the `notes-knowledge-curator` skill.

### Limitations of unrollnow

- **Only works for `/i/status/` URLs.** `/i/article/` (long-form Twitter Articles) is not supported.
- **Single tweet or fully-indexed thread.** Partial threads may have gaps.
- **Rate limiting** at high frequency — back off to ~1 req/sec if scraping multiple tweets.
