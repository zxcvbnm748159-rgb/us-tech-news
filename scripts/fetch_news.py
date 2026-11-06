import json
import os
import re
from datetime import datetime, timedelta, timezone
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
    "IBM", "ADBE", "TSM", "GCTK", "QUCY", "ONDS", "SNDK",
]
DATA_FILE = "data/news.json"
SUMMARY_FILE = "data/market_summary.json"
SENTIMENT_FILE = "data/market_sentiment.json"
TRENDING_FILE = "data/trending_topics.json"
MARKET_PRICES_FILE = "data/market_prices.json"
STOCK_ANALYSIS_FILE = "data/stock_analysis.json"
MAX_KEEP = 300
MAX_TRANSLATE = 15
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
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
                    items[index]["summary_source"] = "gemini"
                category = row.get("category")
                if isinstance(category, str) and category in {"AI", "Hardware", "Financial", "General"}:
                    items[index]["category"] = category
                    items[index]["category_source"] = "gemini"
                if isinstance(row.get("ai_analysis"), str) and row["ai_analysis"].strip():
                    items[index]["ai_analysis"] = row["ai_analysis"].strip()
                    items[index]["analysis_source"] = "gemini"
                impact_level = row.get("impact_level")
                if isinstance(impact_level, str) and impact_level in {"high", "medium", "low"}:
                    items[index]["impact_level"] = impact_level
                    items[index]["impact_source"] = "gemini"
                impact_direction = row.get("impact_direction")
                if isinstance(impact_direction, str) and impact_direction in {"positive", "negative", "neutral"}:
                    items[index]["impact_direction"] = impact_direction
                    items[index]["impact_source"] = "gemini"
                if isinstance(row.get("impact_reason"), str) and row["impact_reason"].strip():
                    items[index]["impact_reason"] = row["impact_reason"].strip()
                    items[index]["impact_source"] = "gemini"
                updated_count += 1

        print(f"AI fully analyzed {updated_count} of {len(items)} items")
    except Exception as ex:
        print("gemini analysis failed:", ex)


def classify_headline_category(title):
    text = (title or "").lower()
    if re.search(r"\b(ai|artificial intelligence|machine learning|generative ai|llm|gpu|accelerator)\b", text):
        return "AI"
    if re.search(r"\b(chip|semiconductor|processor|hardware|device|memory|foundry|wafer)\b", text):
        return "Hardware"
    if re.search(r"\b(earnings|revenue|profit|quarter|guidance|forecast|analyst|stock|shares|valuation|investor|dividend)\b", text):
        return "Financial"
    return "General"


CATEGORY_LABELS_TH = {
    "AI": "ปัญญาประดิษฐ์",
    "Hardware": "ฮาร์ดแวร์และเซมิคอนดักเตอร์",
    "Financial": "การเงินและผลประกอบการ",
    "General": "ข่าวทั่วไป",
}


def apply_headline_fallback(item):
    """Fill missing fields without presenting title-based heuristics as AI analysis."""
    ticker = item.get("ticker") if isinstance(item.get("ticker"), str) else "หุ้น"
    title = item.get("title") if isinstance(item.get("title"), str) else ""
    category = classify_headline_category(title)

    if not item.get("category") or (
        item.get("category") == "General" and item.get("category_source") not in {"gemini", "manual"}
    ):
        item["category"] = category
        item["category_source"] = "headline_rule"

    if not isinstance(item.get("summary_th"), str) or not item["summary_th"].strip():
        item["summary_th"] = (
            f"ข่าว {ticker} ในหมวด{CATEGORY_LABELS_TH[category]} "
            f"อ้างอิงจากพาดหัวต้นฉบับ: {title or 'ไม่มีพาดหัวข่าว'}"
        )
        item["summary_source"] = "headline_fallback"

    if not isinstance(item.get("ai_analysis"), str) or not item["ai_analysis"].strip():
        item["ai_analysis"] = "\n".join([
            "ยังไม่มีผลวิเคราะห์จาก Gemini AI สำหรับข่าวนี้",
            f"พาดหัวที่ใช้ประกอบ: {title or 'ไม่มีพาดหัวข่าว'}",
            "ข้อจำกัด: ระบบมีเพียงพาดหัวข่าว จึงยังยืนยันผลกระทบต่อธุรกิจหรือราคาหุ้นไม่ได้ โปรดอ่านข่าวต้นฉบับ",
        ])
        item["analysis_source"] = "fallback"

    sentiment = item.get("sentiment")
    if sentiment not in {"positive", "negative", "neutral"}:
        sentiment = "neutral"
        item["sentiment"] = sentiment
    item.setdefault("sentiment_source", "headline_vader")

    if item.get("impact_level") not in {"high", "medium", "low"}:
        item["impact_level"] = "low"
    if item.get("impact_direction") not in {"positive", "negative", "neutral"}:
        item["impact_direction"] = sentiment
    if not isinstance(item.get("impact_reason"), str) or not item["impact_reason"].strip():
        item["impact_reason"] = (
            "จัดหมวดเบื้องต้นจากพาดหัวและ sentiment เท่านั้น "
            "ยังไม่ได้ตรวจสอบเนื้อหาข่าวฉบับเต็ม"
        )
    item.setdefault("impact_source", "headline_rule")
    return item


def build_rule_based_daily_summary(items, today):
    counts = calculate_market_sentiment(items)["counts"]
    total = len(items)
    if not total:
        return "\n".join([
            "วันนี้ยังไม่พบข่าวใหม่ที่ยืนยันวันเผยแพร่ได้",
            "ระบบจะแสดงข่าวล่าสุดเมื่อมีข้อมูลจากแหล่งข่าวเข้ามา",
            "โปรดตรวจสอบข่าวต้นฉบับก่อนใช้ประกอบการตัดสินใจ",
        ])

    ticker_counts = {}
    for item in items:
        ticker = item.get("ticker")
        if isinstance(ticker, str) and ticker:
            ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1
    leaders = sorted(ticker_counts.items(), key=lambda row: (-row[1], row[0]))[:3]
    leaders_text = ", ".join(f"{ticker} ({count})" for ticker, count in leaders) or "ยังไม่มีข้อมูลรายหุ้น"
    return "\n".join([
        f"ภาพรวมวันที่ {today}: พบข่าว {total} รายการ — บวก {counts['positive']} · ลบ {counts['negative']} · กลาง {counts['neutral']}",
        f"หุ้นที่มีพาดหัวข่าวมาก: {leaders_text}",
        "ข้อควรระวัง: ตัวเลขนี้นับจาก sentiment ของพาดหัว ไม่ใช่ทิศทางราคา และยังไม่ใช่บทวิเคราะห์ AI",
    ])


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
    now = datetime.now(timezone.utc)
    today = now.astimezone(EASTERN).date()
    today_items = [
        item for item in items
        if (published := parse_news_datetime(item)) is not None
        and published.astimezone(EASTERN).date() == today
    ]
    summary = build_rule_based_daily_summary(today_items, today.isoformat())
    source = "rules"
    api_key = os.environ.get("GEMINI_API_KEY")

    if api_key and today_items:
        headlines = [
            f"[{item.get('ticker', 'N/A')}] ({item.get('sentiment', 'neutral')}) {item.get('title', '')}"
            for item in today_items
        ]
        prompt = (
            "สรุปภาวะตลาดหุ้นเทคโนโลยีสหรัฐวันนี้เป็นภาษาไทยให้สั้นพออ่านจบใน 10 วินาที "
            "เขียน summary_th เป็นข้อความ 3 บรรทัดพอดี: ภาพรวมจากจำนวนข่าวและ sentiment, "
            "หุ้น/ประเด็นที่เด่นจากหัวข้อ, และความเสี่ยงที่ควรตรวจสอบ "
            "ห้ามกล่าวอ้างว่าราคาตลาดขึ้นลงจริงหากไม่มีข้อมูลราคา ห้ามเดาสาเหตุจากพาดหัว "
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
            candidate = result.get("summary_th") if isinstance(result, dict) else None
            summary_lines = [
                line.strip() for line in candidate.splitlines()
                if isinstance(candidate, str) and line.strip()
            ] if isinstance(candidate, str) else []
            if len(summary_lines) == 3:
                summary = "\n".join(summary_lines)
                source = "gemini"
            else:
                print("Gemini daily summary returned an invalid format; using rule-based summary")
        except Exception as ex:
            print("Gemini daily summary failed; using rule-based summary:", ex)
    elif not api_key:
        print("GEMINI_API_KEY unavailable; publishing transparent rule-based daily summary")
    else:
        print("no news published today; publishing an explicit no-news summary")

    os.makedirs("data", exist_ok=True)
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "date": today.isoformat(),
            "summary_th": summary,
            "source_count": len(today_items),
            "source": source,
            "updated_at": now.isoformat(),
        }, f, ensure_ascii=False, indent=2)
    print(f"published {source} daily summary from {len(today_items)} articles")

def generate_stock_analysis(items, now=None):
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=48)
    articles_by_ticker = {ticker: [] for ticker in TICKERS}
    for item in items:
        if not isinstance(item, dict):
            continue
        ticker = item.get("ticker")
        if not isinstance(ticker, str) or ticker not in articles_by_ticker:
            continue
        published = parse_news_datetime(item)
        if published is None or not cutoff <= published.astimezone(timezone.utc) <= now:
            continue
        articles_by_ticker[ticker].append({
            "title": item.get("title", "") if isinstance(item.get("title"), str) else "",
            "summary_th": item.get("summary_th", "") if isinstance(item.get("summary_th"), str) else "",
            "published": published.isoformat(),
        })

    for articles in articles_by_ticker.values():
        articles.sort(key=lambda article: article["published"], reverse=True)

    quotes_by_ticker = {}
    try:
        with open(MARKET_PRICES_FILE, encoding="utf-8") as f:
            market_data = json.load(f)
        quotes = market_data.get("quotes", []) if isinstance(market_data, dict) else []
        if isinstance(quotes, list):
            quotes_by_ticker = {
                quote["symbol"]: quote
                for quote in quotes
                if isinstance(quote, dict) and isinstance(quote.get("symbol"), str)
            }
    except FileNotFoundError:
        print("stock analysis will use news only (market price data not found)")
    except (OSError, ValueError, json.JSONDecodeError) as ex:
        print(f"stock analysis could not read market prices: {ex}")

    active_tickers = [
        ticker for ticker in TICKERS
        if articles_by_ticker[ticker] or ticker in quotes_by_ticker
    ]
    stocks = {}
    context = []
    for ticker in active_tickers:
        articles = articles_by_ticker[ticker][:3]
        quote = quotes_by_ticker.get(ticker, {})
        change_percent = quote.get("change_percent")
        if isinstance(change_percent, (int, float)) and not isinstance(change_percent, bool):
            price_context = f"การเปลี่ยนแปลงจากราคาปิดก่อนหน้า {change_percent:+.2f}%"
        else:
            price_context = "ไม่มีข้อมูลเปอร์เซ็นต์การเปลี่ยนแปลงราคา"
        if articles:
            latest_title = articles[0]["title"] or "ไม่มีพาดหัวข่าว"
            fallback_summary = (
                f"{ticker} มีข่าวที่เกี่ยวข้อง {len(articles_by_ticker[ticker])} รายการในช่วง 48 ชั่วโมงล่าสุด "
                f"พาดหัวล่าสุด: {latest_title} ข้อมูลนี้ยังไม่ยืนยันผลต่อราคาหุ้น"
            )
            points = [
                f"พาดหัวล่าสุด: {latest_title}",
                price_context,
                "ควรอ่านเนื้อหาต้นฉบับและตรวจสอบตัวเลขก่อนสรุปผลกระทบ",
            ]
        else:
            fallback_summary = f"{ticker}: ยังไม่พบข่าวที่เกี่ยวข้องในช่วง 48 ชั่วโมงล่าสุด · {price_context}"
            points = [price_context, "ยังไม่มีหลักฐานข่าวเพียงพอสำหรับอธิบายการเคลื่อนไหว"]
        stocks[ticker] = {
            "ticker": ticker,
            "last_updated": now.isoformat(),
            "summary": fallback_summary,
            "analysis_points": points[:3],
            "analysis_source": "rules",
        }
        context.append({
            "ticker": ticker,
            "change_percent": change_percent
            if isinstance(change_percent, (int, float)) and not isinstance(change_percent, bool)
            else None,
            "headlines": articles,
        })

    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key and context:
        prompt = (
            "คุณคือนักวิเคราะห์หุ้นเทคโนโลยีสหรัฐ สรุปเป็นภาษาไทยโดยใช้เฉพาะข้อมูลราคาและข่าวที่ให้ "
            "ห้ามอ้างว่าข่าวเป็นสาเหตุแน่นอน ห้ามคาดเดาเมื่อไม่มีข้อมูลรองรับ "
            "หากไม่มีข่าวให้บอกว่ายังไม่มีหลักฐานข่าวเพียงพอ "
            "ตอบเป็น JSON object ที่มี key stocks เป็น array โดยแต่ละรายการมี ticker, summary และ analysis_points "
            "(ไม่เกิน 3 ข้อ)\n"
            f"วันที่อ้างอิง (America/New_York): {now.astimezone(EASTERN).date().isoformat()}\n"
            f"ข้อมูลหุ้น: {json.dumps(context, ensure_ascii=False)}"
        )
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            result = json.loads(response.text)
            rows = result.get("stocks") if isinstance(result, dict) else None
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    ticker = row.get("ticker")
                    summary = row.get("summary")
                    if ticker not in stocks or not isinstance(summary, str) or not summary.strip():
                        continue
                    points = row.get("analysis_points")
                    stocks[ticker] = {
                        "ticker": ticker,
                        "last_updated": now.isoformat(),
                        "summary": summary.strip(),
                        "analysis_points": [
                            point.strip() for point in points
                            if isinstance(point, str) and point.strip()
                        ][:3] if isinstance(points, list) else [],
                        "analysis_source": "gemini",
                    }
            else:
                print("Gemini stock analysis returned invalid format; keeping rule-based analysis")
        except Exception as ex:
            print("Gemini stock analysis failed; keeping rule-based analysis:", ex)
    elif not api_key:
        print("GEMINI_API_KEY unavailable; publishing transparent rule-based stock analysis")

    os.makedirs("data", exist_ok=True)
    with open(STOCK_ANALYSIS_FILE, "w", encoding="utf-8") as f:
        json.dump([stocks[ticker] for ticker in TICKERS if ticker in stocks], f, ensure_ascii=False, indent=2)
    print(f"published stock analysis for {len(stocks)} of {len(TICKERS)} tracked stocks")

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
    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    channels = []
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
                send(message)
                sent.append(name)
                print(f"sent high-impact alert to {name}: {item['ticker']}")
            except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as ex:
                print(f"high-impact alert to {name} failed for {item['ticker']}: {ex}")


def main():
    existing = load_existing()
    if not isinstance(existing, list):
        raise ValueError(f"{DATA_FILE} must contain a JSON array; refusing to overwrite invalid data")
    existing = [item for item in existing if isinstance(item, dict)]
    seen = {
        item.get("link") for item in existing
        if isinstance(item.get("link"), str)
    }
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
                "sentiment_source": "headline_vader",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            })

    all_items = (added + existing)[:MAX_KEEP]

    update_daily_market_sentiment(added)
    update_trending_topics(added)
    todo = [
        item for item in all_items
        if item.get("analysis_source") != "gemini" or item.get("summary_source") != "gemini"
    ][:MAX_TRANSLATE]
    translate_and_analyze_batch(todo)
    for item in all_items:
        apply_headline_fallback(item)
    if added or os.environ.get("GENERATE_DAILY_SUMMARY", "true").lower() == "true":
        generate_stock_analysis(all_items)
    else:
        print("skip stock analysis (no new headlines and not a scheduled summary run)")
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
