import json
from pathlib import Path

try:
    from .fetch_news import generate_stock_analysis
except ImportError:
    from fetch_news import generate_stock_analysis


NEWS_FILE = Path("data/news.json")


def load_news_items(path=NEWS_FILE):
    with Path(path).open(encoding="utf-8") as file:
        items = json.load(file)
    if not isinstance(items, list):
        raise ValueError(f"{path} must contain a JSON array of news articles")
    if any(not isinstance(item, dict) for item in items):
        raise ValueError(f"{path} contains a non-object news record")
    return items


def refresh_stock_analysis(news_path=NEWS_FILE):
    items = load_news_items(news_path)
    generate_stock_analysis(items)
    return len(items)


def main():
    count = refresh_stock_analysis()
    print(f"refreshed stock analysis using {count} news articles and the latest market quotes")


if __name__ == "__main__":
    main()
