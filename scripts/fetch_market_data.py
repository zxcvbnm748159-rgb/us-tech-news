import json
import os
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen

TICKERS = (
    "NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "AMD",
    "AVGO", "ORCL", "CRM", "NFLX", "INTC", "QCOM", "PLTR", "SMCI",
    "IBM", "ADBE", "TSM", "GCTK", "QUCY", "ONDS", "SNDK",
)
DATA_FILE = "data/market_prices.json"
USER_AGENT = "Mozilla/5.0 us-tech-news/1.0"


def fetch_chart(ticker, period, interval):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={period}&interval={interval}"
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read())

    chart = payload.get("chart", {})
    if chart.get("error"):
        raise ValueError(f"Yahoo Finance returned an error for {ticker}: {chart['error']}")
    results = chart.get("result") or []
    if not results:
        raise ValueError(f"Yahoo Finance returned no data for {ticker}")
    result = results[0]
    indicators = result.get("indicators", {})
    quotes = indicators.get("quote") or [{}]
    quote = quotes[0]
    history = []
    for index, timestamp in enumerate(result.get("timestamp") or []):
        prices = quote.get("close") or []
        if index >= len(prices) or not isinstance(prices[index], (int, float)):
            continue
        volumes = quote.get("volume") or []
        volume = volumes[index] if index < len(volumes) else None
        history.append({
            "time": timestamp,
            "price": prices[index],
            "volume": volume if isinstance(volume, (int, float)) else None,
        })
    return result.get("meta", {}), history


def number_or_none(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def fetch_stock_data(ticker, now=None):
    now = now or datetime.now(timezone.utc)
    meta, daily_history = fetch_chart(ticker, "5y", "1d")
    _, intraday_history = fetch_chart(ticker, "1d", "5m")
    _, monthly_history = fetch_chart(ticker, "max", "1mo")

    price = number_or_none(meta.get("regularMarketPrice"))
    previous_close = number_or_none(meta.get("chartPreviousClose", meta.get("previousClose")))
    if price is None and intraday_history:
        price = intraday_history[-1]["price"]
    if price is None or previous_close in (None, 0):
        raise ValueError(f"Yahoo Finance returned invalid prices for {ticker}")

    change = price - previous_close
    daily_start = daily_history[0]["time"] if daily_history else 0
    max_history = [point for point in monthly_history if point["time"] < daily_start] + daily_history
    history_by_time = {}
    for key, history in (("1D", intraday_history), ("5D", daily_history[-5:])):
        history_by_time[key] = history

    periods = {
        "1M": 30,
        "6M": 183,
        "1Y": 365,
        "5Y": 365 * 5,
    }
    for key, days in periods.items():
        cutoff = int((now - timedelta(days=days)).timestamp())
        history_by_time[key] = [point for point in daily_history if point["time"] >= cutoff]
    year_start = datetime(now.year, 1, 1, tzinfo=timezone.utc).timestamp()
    history_by_time["YTD"] = [point for point in daily_history if point["time"] >= year_start]
    history_by_time["MAX"] = max_history

    day_high = number_or_none(meta.get("regularMarketDayHigh"))
    day_low = number_or_none(meta.get("regularMarketDayLow"))
    market_state = meta.get("marketState")
    if not isinstance(market_state, str):
        market_state = "REGULAR"
        if meta.get("postMarketPrice") is not None:
            market_state = "POST"
        elif meta.get("preMarketPrice") is not None:
            market_state = "PRE"

    return {
        "quote": {
            "symbol": ticker,
            "price": price,
            "change": change,
            "change_percent": change / previous_close * 100,
            "currency": meta.get("currency", "USD"),
            "market_timestamp": meta.get("regularMarketTime"),
            "market_state": market_state,
            "pre_market_price": number_or_none(meta.get("preMarketPrice")),
            "post_market_price": number_or_none(meta.get("postMarketPrice")),
        },
        "metrics": {
            "open": number_or_none(meta.get("regularMarketOpen")),
            "high": day_high,
            "low": day_low,
            "market_cap": number_or_none(meta.get("marketCap")),
            "average_volume": number_or_none(
                meta.get("averageDailyVolume3Month", meta.get("averageDailyVolume10Day"))
            ),
            "fifty_two_week_high": number_or_none(meta.get("fiftyTwoWeekHigh")),
            "fifty_two_week_low": number_or_none(meta.get("fiftyTwoWeekLow")),
            "eps": number_or_none(meta.get("epsTrailingTwelveMonths")),
            "beta": number_or_none(meta.get("beta")),
            "shares_outstanding": number_or_none(meta.get("sharesOutstanding")),
            "employees": number_or_none(meta.get("fullTimeEmployees")),
            "volume": intraday_history[-1]["volume"] if intraday_history else None,
        },
        "history": history_by_time,
        "name": meta.get("longName") or meta.get("shortName") or ticker,
        "currency": meta.get("currency", "USD"),
    }


def main():
    now = datetime.now(timezone.utc)
    quotes = []
    stocks = {}
    for ticker in TICKERS:
        try:
            stock = fetch_stock_data(ticker, now)
            quotes.append(stock["quote"])
            stocks[ticker] = stock
        except (OSError, ValueError, json.JSONDecodeError) as ex:
            print(f"failed to fetch {ticker}: {ex}")

    if not quotes:
        raise RuntimeError("No stock quotes could be fetched; existing market data was not replaced")

    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": now.isoformat(),
            "quotes": quotes,
            "stocks": stocks,
        }, f, ensure_ascii=False, separators=(",", ":"))
    print(f"updated {len(quotes)} of {len(TICKERS)} stock quotes and chart histories")


if __name__ == "__main__":
    main()
