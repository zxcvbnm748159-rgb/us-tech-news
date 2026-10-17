# us-tech-news

## Fetch news

Install the dependencies and run the updater:

```sh
python -m pip install -r requirements.txt
python scripts/fetch_news.py
```

To translate headlines and generate a daily market summary, set `GEMINI_API_KEY`
in the environment. The GitHub Actions workflow reads this value from the
repository secret with the same name. Without the key, fetching news still
works, but AI analysis, the daily summary, and AI impact alerts are skipped.

## Market data and alerts

The `Update market prices` GitHub Actions workflow refreshes quotes and chart
history for the supported tickers from Yahoo Finance every 15 minutes and
updates `data/market_prices.json`. The dashboard provides watchlists in the
“รายการหลัก” and “หุ้นออปชั่น” categories, price sparklines, and price/volume
charts for 1D, 5D, 1M, 6M, YTD, 1Y, 5Y, and MAX where history is available.
Company metrics and pre-/post-market prices are shown only when Yahoo Finance
provides them; unavailable values are not estimated. Market data can be delayed
and is not a live trading feed. The website displays the latest successful
refresh.

News collection and high-impact alerts run every 15 minutes; the AI daily
summary is refreshed every three hours. GitHub Actions schedules can be delayed
by GitHub.

To receive alerts for AI-classified high-impact positive or negative news, add
this repository secret:

- `DISCORD_WEBHOOK_URL`

Successfully delivered Discord alerts are tracked per article to avoid repeat
notifications.

The news page also provides comparison filters for semiconductor and software
companies, with per-company positive/negative article counts. It offers
one-click filters for AI Infrastructure, EV & Autonomous, and Cloud &
Enterprise themes.

## Daily sentiment and personal notes

The news workflow incrementally records each unique article published on the
current US Eastern calendar day in `data/market_sentiment.json`, so the daily
sentiment score is not limited by the number of articles currently shown on
the website. The score is the percentage of positive articles among positive
and negative headlines; neutral articles are shown in the counts but do not
affect the score. It describes headline sentiment, not actual market returns
or investment advice.

## Portfolio alerts and daily briefing

The `My Portfolio` watchlist is personal to the current browser and is stored
in `localStorage`; it is not sent to the news bot or shared with other users.
When refreshed news contains an AI-classified high-impact article tagged with
one of the selected tickers, the page highlights it in the portfolio alert
panel. The news feed refreshes every 15 minutes while the page is open.

The AI daily market briefing is requested as exactly three concise Thai lines:
market sentiment, notable stocks/topics, and risks or items to watch. It is a
text briefing; no audio is generated.

## Trending topics

`data/trending_topics.json` contains popular ticker and curated topic tags
calculated from unique stored headlines in the rolling seven-day window.
Topic tags include common aliases (for example, GPU and semiconductor for AI
Chip) and can be clicked to filter matching headlines. The topic taxonomy is
rule-based and does not claim to be unrestricted semantic search.

Readers can save a personal note and an optional USD target price for each
article. These notes and bookmarks are stored only in that browser's
`localStorage` and are included in the saved-articles view.

## Dashboard interface

The responsive dashboard uses a market overview above a three-column desktop
layout for filters, the news feed, and high-impact/trending stories. It follows
the system light/dark preference, provides skeleton loading states, and uses
toast notifications for bookmark, note, and clipboard actions.