import os, json, re, hashlib, html
from datetime import datetime, timezone
from pathlib import Path
import feedparser
import trafilatura
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
SOURCES_FILE = ROOT / "data" / "sources.json"
DEFAULT_SOURCES = [
    {"name": "Tom's Hardware", "url": "https://www.tomshardware.com/feeds/all", "enabled": True},
    {"name": "Wccftech", "url": "https://wccftech.com/feed/", "enabled": True},
    {"name": "TechPowerUp", "url": "https://www.techpowerup.com/rss/news", "enabled": True},
    {"name": "AnandTech", "url": "https://www.anandtech.com/rss/", "enabled": True},
    {"name": "VideoCardz", "url": "https://videocardz.com/feed", "enabled": True},
    {"name": "ServeTheHome", "url": "https://www.servethehome.com/feed/", "enabled": True},
]
KEYWORDS = {
    "GPU": ["gpu", "graphics card", "geforce", "radeon", "rtx", "arc gpu", "graphics processor"],
    "CPU": ["cpu", "processor", "ryzen", "core ultra", "threadripper", "xeon", "epyc"],
    "Memory": ["ram", "ddr5", "ddr6", "ssd", "nvme", "dram", "memory", "storage"],
    "Other": ["motherboard", "pc case", "cooler", "power supply", "psu", "hardware", "gaming monitor", "pc component"],
}

def category(value):
    value = value.lower()
    for name, words in KEYWORDS.items():
        if any(word in value for word in words):
            return name
    return None

def load_sources():
    if not SOURCES_FILE.exists():
        SOURCES_FILE.write_text(json.dumps(DEFAULT_SOURCES, indent=2), encoding="utf-8")
    try:
        configured = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
        if isinstance(configured, dict):
            configured = configured.get("sources", [])
        valid = [s for s in configured if isinstance(s, dict) and s.get("enabled", True)
                 and s.get("name") and str(s.get("url", "")).startswith(("http://", "https://"))]
        return valid or DEFAULT_SOURCES
    except Exception as error:
        print(f"Could not parse sources.json: {error}; using defaults.")
        return DEFAULT_SOURCES

def clean_html(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()

def get_full_article(url, rss_html):
    """Prefer the publicly readable article body; fall back to the publisher's RSS content."""
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            extracted = trafilatura.extract(
                downloaded, output_format="html", include_comments=False,
                include_tables=True, include_images=True, include_links=True,
                favor_recall=True
            )
            if extracted and len(clean_html(extracted)) > max(500, len(clean_html(rss_html)) * 1.15):
                print(f"Fetched full article body: {url}")
                return extracted[:50000]
    except Exception as error:
        print(f"Full article extraction fallback [{url}]: {error}")
    return html.unescape(rss_html or "")

def translate_text(client, text_value):
    if not client or not text_value:
        return ""
    try:
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            input=[
                {"role": "system", "content": "Translate this hardware-news headline into concise, natural Arabic. Return only the translation."},
                {"role": "user", "content": text_value},
            ],
        )
        return response.output_text.strip()
    except Exception as error:
        print(f"Headline translation fallback: {error}")
        return ""

def translate_html(client, title, content):
    if not client or not content:
        return ""
    try:
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            input=[
                {"role": "system", "content": "Translate the supplied hardware-news article HTML into natural Arabic. Preserve every HTML tag, nesting, attributes, links, lists, headings, paragraphs, emphasis, tables, images and line breaks exactly. Translate only visible text. Do not summarize, omit sections, or invent facts. Return the complete translated HTML only."},
                {"role": "user", "content": f"Headline: {title}\\nArticle HTML:\\n{content[:30000]}"},
            ],
        )
        return response.output_text.strip()
    except Exception as error:
        print(f"HTML translation fallback: {error}")
        return ""

def summarize(client, title, description, language="English"):
    clean = clean_html(description)
    if not client:
        return clean[:420] or ("اقرأ التفاصيل من المصدر الأصلي." if language == "Arabic" else "Open the original report for full details.")
    try:
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            input=[
                {"role": "system", "content": f"Write a concise, factual 2-sentence {language} hardware news summary from the supplied headline and feed description. Do not invent details. Return only the summary."},
                {"role": "user", "content": f"Headline: {title}\\nFeed description: {description}"},
            ],
        )
        return response.output_text.strip()
    except Exception as error:
        print(f"{language} summary fallback: {error}")
        return clean[:420] or "Open the original report for full details."

def main():
    client = OpenAI() if os.getenv("OPENAI_API_KEY") else None
    if not client:
        print("OPENAI_API_KEY is not configured: Arabic translations will remain unavailable.")
    articles, seen, feed_errors = [], set(), []
    sources = load_sources()
    for source in sources:
        name, url = source["name"], source["url"].strip()
        try:
            feed = feedparser.parse(url, request_headers={"User-Agent": "HardwarePulse/1.0 (+https://github.com/michaelgad121109-cmd/hardware-pulse)"})
            if getattr(feed, "bozo", False):
                print(f"Feed warning [{name}]: {feed.get('bozo_exception')}")
            if not feed.entries:
                feed_errors.append(name)
                print(f"No entries returned by {name}: {url}")
                continue
            added = 0
            for entry in feed.entries[:50]:
                if len(articles) >= 80:
                    break
                title = (entry.get("title") or "").strip()
                link = entry.get("link", "")
                description = entry.get("summary") or entry.get("description") or ""
                content_blocks = entry.get("content") or []
                rss_html = (content_blocks[0].get("value", "") if content_blocks else "") or entry.get("summary_detail", {}).get("value", "") or description
                if not rss_html:
                    rss_html = f"<p>{title}</p>"
                cat = category(title + " " + clean_html(description))
                if not title or not link.startswith(("http://", "https://")) or not cat:
                    continue
                key = hashlib.sha256(link.encode()).hexdigest()
                if key in seen:
                    continue
                seen.add(key)
                full_html = get_full_article(link, rss_html)
                published = entry.get("published") or entry.get("updated") or datetime.now(timezone.utc).isoformat()
                articles.append({
                    "title": title,
                    "title_ar": translate_text(client, title),
                    "summary": summarize(client, title, description, "English"),
                    "summary_ar": summarize(client, title, description, "Arabic") if client else "",
                    "content_html": full_html,
                    "content_ar_html": translate_html(client, title, full_html),
                    "category": cat, "source": name, "url": link, "published_at": published,
                })
                added += 1
            print(f"{name}: parsed {len(feed.entries)} entries, added {added} hardware stories.")
        except Exception as error:
            feed_errors.append(name)
            print(f"Could not read {name}: {error}")

    if not articles:
        raise SystemExit("No hardware articles were collected. Keeping the existing news file; check RSS URLs and workflow logs.")
    articles.sort(key=lambda item: item["published_at"], reverse=True)
    payload = {"updated_at": datetime.now(timezone.utc).isoformat(), "sources_checked": len(sources),
               "feed_errors": feed_errors, "articles": articles[:80]}
    (ROOT / "data" / "news.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(payload['articles'])} hardware stories from {len(sources)} sources.")

if __name__ == "__main__":
    main()
