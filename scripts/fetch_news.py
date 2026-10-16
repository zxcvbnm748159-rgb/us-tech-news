import json, os
from datetime import datetime, timezone
import feedparser
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

TICKERS = [
    "NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "AMD",
    "AVGO", "ORCL", "CRM", "NFLX", "INTC", "QCOM", "PLTR", "SMCI",
    "IBM", "ADBE", "TSM",
]
DATA_FILE = "data/news.json"
MAX_KEEP = 300

analyzer = SentimentIntensityAnalyzer()

def load_existing():
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def get_sentiment(text):
    score = analyzer.polarity_scores(text)["compound"]
    if score >= 0.2:
        return "positive"
    if score <= -0.2:
        return "negative"
    return "neutral"

def main():
    existing = load_existing()
    seen = {x["link"] for x in existing}
    added = []
    for t in TICKERS:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={t}&region=US&lang=en-US"
        feed = feedparser.parse(url)
        for e in feed.entries[:5]:
            link = e.get("link", "")
            if not link or link in seen:
                continue
            seen.add(link)
            title = e.get("title", "")
            added.append({
                "ticker": t,
                "title": title,
                "link": link,
                "published": e.get("published", ""),
                "summary_th": "",
                "sentiment": get_sentiment(title),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            })

    all_items = (added + existing)[:MAX_KEEP]
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)
    print(f"added {len(added)} items, total {len(all_items)}")

if __name__ == "__main__":
    main()