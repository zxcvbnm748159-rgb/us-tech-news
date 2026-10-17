import json
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import feedparser
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from google import genai
from google.genai import types

TICKERS = [
    "NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "AMD",
    "AVGO", "ORCL", "CRM", "NFLX", "INTC", "QCOM", "PLTR", "SMCI",
    "IBM", "ADBE", "TSM",
]
DATA_FILE = "data/news.json"
SUMMARY_FILE = "data/market_summary.json"
SENTIMENT_FILE = "data/market_sentiment.json"
TRENDING_FILE = "data/trending_topics.json"
MAX_KEEP = 300
MAX_TRANSLATE = 15
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
EASTERN = ZoneInfo("America/New_York")
TRENDING_TERMS = {
    "AI Chip": (r"\b(?:AI chips?|GPU|accelerators?|semiconductors?)\b",
                ("AI chip", "GPU", "accelerator", "semiconductor")),
    "Robotaxi": (r"\b(?:robotaxis|robotaxi|autonomous driving|self-driving)\b",
                 ("robotaxi", "autonomous driving", "self-driving")),
    "Antitrust": (r"\b(?:antitrust|competition lawsuit|regulatory probe|monopoly)\b",
                  ("antitrust", "competition lawsuit", "regulatory probe", "monopoly")),
    "Data Center": (r"\b(?:data cent(?:er|re)s?|AI infrastructure)\b",
                    ("data center", "AI infrastructure")),
    "Earnings": (r"\b(?:earnings|quarterly results|revenue guidance|profit forecast)\b",
                 ("earnings", "quarterly results", "revenue guidance", "profit forecast")),
    "Cloud": (r"\b(?:cloud computing|cloud services|Azure|AWS|Google Cloud)\b",
              ("cloud computing", "cloud services", "Azure", "AWS", "Google Cloud")),
}

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


def translate_and_analyze_batch(items):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or not items:
        print("skip translate/analyze (no key or no items)")
        return

    lines = [f"{i}. [{item['ticker']}] {item['title']}" for i, item in enumerate(items)]
    prompt = (
        "คุณคือนักวิเคราะห์หุ้นเทคโนโลยีสหรัฐมืออาชีพ\n"
        "สำหรับแต่ละหัวข้อข่าวข้างล่างนี้ ให้:\n"
        "1. แปลและสรุปเป็นภาษาไทยกระชับ 1 ประโยค (เก็บชื่อบริษัท/หุ้นเป็นอังกฤษ) ลงใน 'summary_th'\n"
        "2. จัดหมวดหมู่ข่าวจากตัวเลือกเหล่านี้เท่านั้น: 'AI', 'Hardware', 'Financial', 'General' ลงใน 'category'\n"
        "3. วิเคราะห์เชิงลึกเป็นภาษาไทย 3 ประเด็นกระชับ: ผลกระทบต่อหุ้น, โอกาสและความเสี่ยงระยะสั้น-กลาง, และมุมมองเชิงกลยุทธ์ ลงใน 'ai_analysis'\n"
        "4. กำหนด 'impact_level' เป็น 'high', 'medium' หรือ 'low' ตามความสำคัญที่มีแนวโน้มกระทบราคาหุ้นอย่างมีนัยสำคัญ\n"
        "5. กำหนด 'impact_direction' เป็น 'positive', 'negative' หรือ 'neutral' และเขียนเหตุผลสั้นๆ ภาษาไทยใน 'impact_reason'\n\n"
        'ตอบกลับเป็น JSON array เท่านั้น ในรูปแบบโครงสร้างนี้:\n'
        '[{"id":0,"summary_th":"...","category":"AI","ai_analysis":"...","impact_level":"high","impact_direction":"negative","impact_reason":"..."}]\n\n'
        + "\n".join(lines)
    )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        results = json.loads(response.text)
        if not isinstance(results, list):
            raise ValueError("Gemini response must be a JSON array")

        updated_count = 0
        for row in results:
            if not isinstance(row, dict):
                continue
            index = row.get("id")
            if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(items):
                if isinstance(row.get("summary_th"), str) and row["summary_th"].strip():
                    items[index]["summary_th"] = row["summary_th"].strip()
                category = row.get("category")
                if isinstance(category, str) and category in {"AI", "Hardware", "Financial", "General"}:
                    items[index]["category"] = category
                if isinstance(row.get("ai_analysis"), str) and row["ai_analysis"].strip():
                    items[index]["ai_analysis"] = row["ai_analysis"].strip()
                impact_level = row.get("impact_level")
                if isinstance(impact_level, str) and impact_level in {"high", "medium", "low"}:
                    items[index]["impact_level"] = impact_level
                impact_direction = row.get("impact_direction")
                if isinstance(impact_direction, str) and impact_direction in {"positive", "negative", "neutral"}:
                    items[index]["impact_direction"] = impact_direction
                if isinstance(row.get("impact_reason"), str) and row["impact_reason"].strip():
                    items[index]["impact_reason"] = row["impact_reason"].strip()
                updated_count += 1

        print(f"AI fully analyzed {updated_count} of {len(items)} items")
    except Exception as ex:
        print("gemini analysis failed:", ex)


def parse_news_datetime(item):
    try:
        value = parsedate_to_datetime(item.get("published", ""))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value
    except (TypeError, ValueError, OverflowError):
        try:
            value = datetime.fromisoformat(item.get("fetched_at", ""))
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value
        except (TypeError, ValueError):
            return None


def calculate_market_sentiment(items):
    counts = {"positive": 0, "negative": 0, "neutral": 0}
    for item in items:
        sentiment = item.get("sentiment")
        counts[sentiment if isinstance(sentiment, str) and sentiment in counts else "neutral"] += 1

    directional_count = counts["positive"] + counts["negative"]
    score = round(counts["positive"] / directional_count * 100) if directional_count else None
    if score is None:
        label = "No data"
    elif score >= 60:
        label = "Bullish"
    elif score <= 40:
        label = "Bearish"
    else:
        label = "Mixed"
    return {
        "score": score,
        "label": label,
        "counts": counts,
        "total": sum(counts.values()),
    }


def update_daily_market_sentiment(new_items):
    today = datetime.now(EASTERN).date()
    try:
        with open(SENTIMENT_FILE, encoding="utf-8") as f:
            daily_data = json.load(f)
    except FileNotFoundError:
        daily_data = {}

    if daily_data.get("date") != today.isoformat():
        daily_data = {"date": today.isoformat(), "articles": []}
    if not isinstance(daily_data.get("articles"), list):
        raise ValueError(f"{SENTIMENT_FILE} articles must be a list")

    seen_links = {
        article.get("link")
        for article in daily_data["articles"]
        if isinstance(article, dict) and isinstance(article.get("link"), str)
    }
    for item in new_items:
        published = parse_news_datetime(item)
        if published is None or published.astimezone(EASTERN).date() != today:
            continue
        link = item.get("link")
        if not isinstance(link, str) or not link or link in seen_links:
            continue
        daily_data["articles"].append({
            "link": link,
            "sentiment": item.get("sentiment", "neutral"),
        })
        seen_links.add(link)

    summary = calculate_market_sentiment(daily_data["articles"])
    os.makedirs("data", exist_ok=True)
    with open(SENTIMENT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "date": today.isoformat(),
            **summary,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "articles": daily_data["articles"],
        }, f, ensure_ascii=False, indent=2)
    print(
        f"updated daily market sentiment: {summary['label']} "
        f"({summary['score'] if summary['score'] is not None else 'N/A'}), "
        f"{summary['total']} articles"
    )


def generate_daily_summary(items):
    api_key = os.environ.get("GEMINI_API_KEY")
    today = datetime.now(EASTERN).date()
    today_items = [
        item for item in items
        if (published := parse_news_datetime(item)) is not None
        and published.astimezone(EASTERN).date() == today
    ]
    if not api_key:
        print("skip daily summary (no GEMINI_API_KEY)")
        return
    if not today_items:
        print("skip daily summary (no news published today)")
        return

    headlines = [
        f"[{item['ticker']}] ({item.get('sentiment', 'neutral')}) {item['title']}"
        for item in today_items
    ]
    prompt = (
        "สรุปภาวะตลาดหุ้นเทคโนโลยีสหรัฐวันนี้เป็นภาษาไทยให้สั้นพออ่านจบใน 10 วินาที "
        "เขียน summary_th เป็นข้อความ 3 บรรทัดพอดี (คั่นแต่ละบรรทัดด้วย newline): "
        "บรรทัด 1 ระบุภาพรวม/ทิศทางจาก sentiment ข่าว, บรรทัด 2 ระบุหุ้นหรือประเด็นเด่น, "
        "บรรทัด 3 ระบุความเสี่ยง/สิ่งที่ต้องติดตาม "
        "อย่ากล่าวอ้างว่าราคาตลาดขึ้นลงจริงถ้าไม่มีข้อมูลราคา และอย่าคาดเดานอกเหนือจากหัวข้อข่าว "
        "ตอบเป็น JSON object ที่มี key summary_th เท่านั้น\n\n"
        + "\n".join(headlines)
    )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        result = json.loads(response.text)
        summary = result.get("summary_th") if isinstance(result, dict) else None
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("Gemini daily summary must contain non-empty summary_th")
        summary_lines = [line.strip() for line in summary.splitlines() if line.strip()]
        if len(summary_lines) != 3:
            raise ValueError("Gemini daily summary must contain exactly three non-empty lines")
        summary = "\n".join(summary_lines)

        os.makedirs("data", exist_ok=True)
        with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "date": today.isoformat(),
                "summary_th": summary.strip(),
                "source_count": len(today_items),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }, f, ensure_ascii=False, indent=2)
        print(f"generated daily summary from {len(today_items)} articles")
    except Exception as ex:
        print("Gemini daily summary failed:", ex)


def build_trending_topics(articles, now=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(EASTERN).date().toordinal()
    cutoff = today - 6
    recent = []
    seen_links = set()
    for item in articles:
        if not isinstance(item, dict):
            continue
        published = parse_news_datetime(item)
        link = item.get("link")
        title = item.get("title")
        ticker = item.get("ticker")
        if (
            published is None
            or not cutoff <= published.astimezone(EASTERN).date().toordinal() <= today
            or not isinstance(link, str)
            or not link
            or link in seen_links
            or not isinstance(title, str)
        ):
            continue
        seen_links.add(link)
        recent.append((ticker, title))

    topics = []
    for label, (pattern, search_terms) in TRENDING_TERMS.items():
        matching = sum(bool(re.search(pattern, title, re.IGNORECASE)) for _, title in recent)
        if matching:
            topics.append({
                "label": label, "query": label, "search_terms": list(search_terms),
                "count": matching, "kind": "topic",
            })
    for ticker in sorted({ticker for ticker, _ in recent if isinstance(ticker, str)}):
        matching = sum(article_ticker == ticker for article_ticker, _ in recent)
        topics.append({
            "label": ticker, "query": ticker, "search_terms": [ticker],
            "count": matching, "kind": "ticker",
        })

    topics.sort(key=lambda topic: (-topic["count"], topic["label"]))
    return {
        "date": now.astimezone(EASTERN).date().isoformat(),
        "window_days": 7,
        "source_count": len(recent),
        "topics": topics[:12],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def update_trending_topics(new_items):
    try:
        with open(TRENDING_FILE, encoding="utf-8") as f:
            stored = json.load(f)
    except FileNotFoundError:
        stored = {}

    articles = stored.get("articles", []) if isinstance(stored, dict) else []
    if not isinstance(articles, list):
        raise ValueError(f"{TRENDING_FILE} articles must be a list")
    articles.extend(new_items)
    now = datetime.now(timezone.utc)
    trending = build_trending_topics(articles, now)
    today = now.astimezone(EASTERN).date().toordinal()
    cutoff = today - 6
    rolling_articles = []
    seen_links = set()
    for item in articles:
        published = parse_news_datetime(item) if isinstance(item, dict) else None
        link = item.get("link") if isinstance(item, dict) else None
        article_day = published.astimezone(EASTERN).date().toordinal() if published else None
        if (
            isinstance(link, str)
            and link
            and link not in seen_links
            and article_day is not None
            and cutoff <= article_day <= today
        ):
            rolling_articles.append(item)
            seen_links.add(link)

    os.makedirs("data", exist_ok=True)
    with open(TRENDING_FILE, "w", encoding="utf-8") as f:
        json.dump({**trending, "articles": rolling_articles}, f, ensure_ascii=False, indent=2)
    print(f"updated 7-day trending topics from {trending['source_count']} articles")


def post_json(url, payload):
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "us-tech-news/1.0"},
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        body = response.read()
        return json.loads(body) if body else {}


def notify_high_impact(items):
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    channels = []
    if bool(telegram_token) != bool(telegram_chat_id):
        print("Telegram alerts skipped (configure both TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)")
    if telegram_token and telegram_chat_id:
        channels.append(("telegram", lambda message: post_json(
            f"https://api.telegram.org/bot{telegram_token}/sendMessage",
            {"chat_id": telegram_chat_id, "text": message},
        )))
    if discord_webhook:
        channels.append(("discord", lambda message: post_json(
            discord_webhook, {"content": message},
        )))
    if not channels:
        print("skip high-impact alerts (no notification channel configured)")
        return

    for item in items:
        if item.get("impact_level") != "high" or item.get("impact_direction") not in {"positive", "negative"}:
            continue
        sent = item.setdefault("notifications_sent", [])
        if not isinstance(sent, list):
            sent = item["notifications_sent"] = []
        message = (
            f"🚨 ข่าวหุ้นเทคผลกระทบสูง: {item['ticker']} "
            f"({item['impact_direction'].upper()})\n{item['title']}\n"
            f"{item.get('impact_reason') or item.get('summary_th') or ''}\n{item['link']}"
        )
        for name, send in channels:
            if name in sent:
                continue
            try:
                response = send(message)
                if name == "telegram" and (not isinstance(response, dict) or not response.get("ok")):
                    raise ValueError("Telegram API did not confirm delivery")
                sent.append(name)
                print(f"sent high-impact alert to {name}: {item['ticker']}")
            except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as ex:
                print(f"high-impact alert to {name} failed for {item['ticker']}: {ex}")


def main():
    existing = load_existing()
    seen = {item["link"] for item in existing}
    added = []
    for ticker in TICKERS:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            link = entry.get("link", "")
            if not link or link in seen:
                continue
            seen.add(link)
            title = entry.get("title", "")
            added.append({
                "ticker": ticker,
                "title": title,
                "link": link,
                "published": entry.get("published", ""),
                "summary_th": "",
                "category": "General",
                "ai_analysis": "",
                "impact_level": "low",
                "impact_direction": "neutral",
                "sentiment": get_sentiment(title),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            })

    all_items = (added + existing)[:MAX_KEEP]

    update_daily_market_sentiment(added)
    update_trending_topics(added)
    todo = [item for item in all_items if not item.get("ai_analysis")][:MAX_TRANSLATE]
    translate_and_analyze_batch(todo)
    if os.environ.get("GENERATE_DAILY_SUMMARY", "true").lower() == "true":
        generate_daily_summary(all_items)
    else:
        print("skip daily summary (not scheduled for this run)")
    notify_high_impact(all_items)

    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)
    print(f"added {len(added)} items, total {len(all_items)}")


if __name__ == "__main__":
    main()
