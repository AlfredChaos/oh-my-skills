# Agent Reach — Troubleshooting & Fallbacks

## Jina.ai Reader Timeout → Fallback Chain

When `curl -s "https://r.jina.ai/<URL>"` times out (exit code 28), do NOT retry jina.ai. Use the fallback chain:

1. **Browser fetch** — `browser_navigate(url)` → `browser_snapshot(full=true)` → scroll through content → `browser_console` for JS-driven content
2. **Urllib direct fetch** — Python `urllib.request` with Mozilla User-Agent, then strip scripts/styles/HTML tags with regex

### Urllib + regex strip pattern

```python
import urllib.request
import re

url = "https://example.com/article"
req = urllib.request.Request(url, headers={
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
})
resp = urllib.request.urlopen(req, timeout=30)
content = resp.read().decode('utf-8', errors='replace')

# Strip JS and CSS
content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL)
# Strip HTML tags
content = re.sub(r'<[^>]+>', ' ', content)
# Normalize whitespace
content = re.sub(r'\s+', ' ', content)
```

### When to prefer each method

| Method | Best for | Limitation |
|--------|----------|------------|
| `curl -s "https://r.jina.ai/<URL>"` | Clean articles, docs | Times out on some sites |
| `browser_navigate` | JS-heavy pages, dynamic content | Slow, triggers bot detection |
| `urllib + regex` | Fallback when both above fail | Loses JS-rendered content |

## Git Discipline for Vault Operations

When ingesting a URL into the Notes vault:

1. **Before writing**: `git status --short --branch` in vault root to check dirty state
2. **Stage only workflow files**: `git add raw/xxx wiki/yyy wiki/index.md`
3. **Commit**: Conventional Commit message, e.g. `docs: ingest Anthropic long-running agents harness article`
4. **Push after commit**: `git push`
5. **Notify user**: Raw path, wiki path, commit hash, push target

**Important**: Do NOT stage unrelated dirty files. If vault has other uncommitted changes, stage only the files from this ingest workflow.

## Vault Path Reference

- Vault root: `/Users/alfredchaos/home/Notes`
- Raw layer: `raw/articles/`, `raw/videos/`, `raw/papers/`
- Wiki layer: `wiki/summaries/`, `wiki/concepts/`
- Index: `wiki/index.md` (update on every ingest)