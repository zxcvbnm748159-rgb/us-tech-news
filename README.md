# us-tech-news

## Fetch news

Install the dependencies and run the updater:

```sh
python -m pip install -r requirements.txt
python scripts/fetch_news.py
```

To translate headlines into Thai, set `GEMINI_API_KEY` in the environment.
The GitHub Actions workflow reads this value from the repository secret with
the same name. Without the key, fetching news still works and translation is
skipped.