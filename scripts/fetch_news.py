import json, os
from datetime import datetime, timezone
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
MAX_KEEP = 300
MAX_TRANSLATE = 20  
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")

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
        
    lines = [f"{i}. [{it['ticker']}] {it['title']}" for i, it in enumerate(items)]
    
    prompt = (
        "คุณคือนักวิเคราะห์การลงทุนหุ้นเทคโนโลยีสหรัฐ\n"
        "สำหรับแต่ละหัวข้อข่าวข้างล่างนี้ ให้:\n"
        "1. แปลและสรุปเป็นภาษาไทยกระชับ 1 ประโยค (เก็บชื่อบริษัท/หุ้นเป็นอังกฤษ)\n"
        "2. จัดหมวดหมู่ข่าวจากตัวเลือกเหล่านี้เท่านั้น: 'AI', 'Hardware', 'Financial', 'General'\n\n"
        'ตอบกลับเป็น JSON array เท่านั้น ในรูปแบบโครงสร้างนี้:\n'
        '[{"id": 0, "summary_th": "...", "category": "AI"}]\n\n'
        + "\n".join(lines)
    )
    
    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        results = json.loads(resp.text)
        if not isinstance(results, list):
            raise ValueError("Gemini response must be a JSON array")

        updated_count = 0
        for row in results:
            if not isinstance(row, dict):
                continue
            i = row.get("id")
            if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(items):
                if isinstance(row.get("summary_th"), str) and row["summary_th"].strip():
                    items[i]["summary_th"] = row["summary_th"].strip()
                if isinstance(row.get("category"), str):
                    items[i]["category"] = row["category"].strip()
                updated_count += 1
                
        print(f"AI enhanced {updated_count} of {len(items)} items")
    except Exception as ex:
        print("gemini analysis failed:", ex)

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
                "category": "General",
                "sentiment": get_sentiment(title),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            })

    all_items = (added + existing)[:MAX_KEEP]

    todo = [x for x in all_items if not x.get("summary_th")][:MAX_TRANSLATE]
    translate_and_analyze_batch(todo)

    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)
    print(f"added {len(added)} items, total {len(all_items)}")

if __name__ == "__main__":
    main()