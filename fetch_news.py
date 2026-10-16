import json, os, time
from datetime import datetime, timezone
import feedparser
import anthropic

TICKERS = ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "AMD"]
DATA_FILE = "data/news.json"
MAX_NEW_PER_RUN = 20      # จำกัดค่าใช้จ่ายต่อรอบ
MAX_KEEP = 300            # เก็บข่าวสะสมสูงสุด

client = anthropic.Anthropic()  # อ่าน ANTHROPIC_API_KEY จาก environment

def load_existing():
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def fetch_candidates():
    items = []
    for t in TICKERS:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={t}&region=US&lang=en-US"
        feed = feedparser.parse(url)
        for e in feed.entries[:5]:
            items.append({
                "ticker": t,
                "title": e.get("title", ""),
                "link": e.get("link", ""),
                "published": e.get("published", ""),
                "snippet": e.get("summary", "")[:500],
            })
    return items

def summarize(item):
    prompt = f"""สรุปข่าวหุ้นต่อไปนี้เป็นภาษาไทย โดยใช้เฉพาะข้อมูลที่ให้มา ห้ามเดาหรือเพิ่มข้อมูลเอง
ตอบเป็น JSON เท่านั้น ไม่มีข้อความอื่น รูปแบบ:
{{"summary_th": "สรุป 1-2 ประโยค", "sentiment": "positive|negative|neutral"}}

หุ้น: {item['ticker']}
หัวข้อ: {item['title']}
เนื้อหาย่อ: {item['snippet']}"""
    resp = client.messages.create(
        model="claude-haiku-5-5",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip().replace("```json", "").replace("```", "")
    return json.loads(text)

def main():
    existing = load_existing()
    seen = {x["link"] for x in existing}
    new_items = [c for c in fetch_candidates() if c["link"] and c["link"] not in seen]
    new_items = new_items[:MAX_NEW_PER_RUN]

    added = []
    for item in new_items:
        try:
            result = summarize(item)
            item.update(result)
            item["fetched_at"] = datetime.now(timezone.utc).isoformat()
            item.pop("snippet", None)   # ไม่เก็บเนื้อหาต้นฉบับ
            added.append(item)
            time.sleep(0.5)
        except Exception as ex:
            print("skip:", item["title"], ex)

    all_items = (added + existing)[:MAX_KEEP]
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)
    print(f"added {len(added)} items, total {len(all_items)}")

if __name__ == "__main__":
    main()
