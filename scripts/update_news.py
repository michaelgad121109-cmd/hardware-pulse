import os, json, re, hashlib
from datetime import datetime, timezone
from pathlib import Path
import feedparser
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    ("Tom's Hardware", "https://www.tomshardware.com/feeds/all"),
    ("Wccftech", "https://wccftech.com/feed/"),
    ("TechPowerUp", "https://www.techpowerup.com/rss/news"),
    ("AnandTech", "https://www.anandtech.com/rss/"),
    ("VideoCardz", "https://videocardz.com/feed"),
    ("ServeTheHome", "https://www.servethehome.com/feed/"),
]
KEYWORDS = {
    "GPU": ["gpu", "graphics card", "geforce", "radeon", "rtx", "arc gpu", "graphics processor"],
    "CPU": ["cpu", "processor", "ryzen", "core ultra", "threadripper", "xeon", "epyc"],
    "Memory": ["ram", "ddr5", "ddr6", "ssd", "nvme", "dram", "memory", "storage"],
    "Other": ["motherboard", "pc case", "cooler", "power supply", "psu", "hardware"],
}

def category(text):
    text = text.lower()
    for name, words in KEYWORDS.items():
        if any(word in text for word in words):
            return name
    return None

def summarize(client, title, description):
    clean = re.sub(r"<[^>]+>", "", description or "").strip()
    if not client:
        return clean[:380] or "Open the original report for full details."
    try:
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            input=[
                {"role": "system", "content": "Write a concise, factual 2-sentence English news digest summary from the supplied headline and short feed description. Do not invent details, do not copy long phrases, and clearly qualify uncertainty. Return only the summary."},
                {"role": "user", "content": f"Headline: {title}\nFeed description: {description}"},
            ],
        )
        return response.output_text.strip()
    except Exception as error:
        print("Summary fallback:", error)
        return clean[:380] or "Open the original report for full details."

def main():
    client = OpenAI() if os.getenv("OPENAI_API_KEY") else None
    articles, seen = [], set()
    for source, url in SOURCES:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:35]:
                title = (entry.get("title") or "").strip()
                link = entry.get("link", "")
                description = entry.get("summary", "")
                cat = category(title + " " + description)
                if not title or not link.startswith("http") or not cat:
                    continue
                key = hashlib.sha256(link.encode()).hexdigest()
                if key in seen:
                    continue
                seen.add(key)
                articles.append({
                    "title": title,
                    "summary": summarize(client, title, description),
                    "category": cat,
                    "source": source,
                    "url": link,
                    "published_at": entry.get("published", datetime.now(timezone.utc).isoformat()),
                })
        except Exception as error:
            print(f"Could not read {source}: {error}")
    articles.sort(key=lambda item: item["published_at"], reverse=True)
    payload = {"updated_at": datetime.now(timezone.utc).isoformat(), "articles": articles[:60]}
    (ROOT / "data/news.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(payload['articles'])} hardware stories.")

if __name__ == "__main__":
    main()
