(function (root) {
  "use strict";
  const NEWS_WINDOW_MS = 48 * 60 * 60 * 1000;
  const PRICE_STALE_MS = 2 * 60 * 60 * 1000;

  function median(values) {
    if (!values.length) return null;
    const sorted = values.slice().sort((a, b) => a - b);
    const middle = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
  }

  function volumeRatio(stock) {
    const history = stock && stock.history && stock.history["1D"];
    if (!Array.isArray(history)) return null;
    const bars = history.filter(point =>
      point && Number.isFinite(point.time) &&
      Number.isFinite(point.volume) && point.volume > 0
    );
    if (bars.length < 6) return null;
    const latest = bars[bars.length - 1].volume;
    const baseline = median(bars.slice(-13, -1).map(point => point.volume));
    return baseline > 0 ? latest / baseline : null;
  }

  function recentNews(items, nowMs) {
    return items.filter(item => {
      if (!item || typeof item.ticker !== "string") return false;
      if (item.impact_level !== "high" && item.impact_level !== "medium") return false;
      const rawDate = item.published || item.fetched_at;
      const timestamp = rawDate ? Date.parse(rawDate) : NaN;
      return Number.isFinite(timestamp) &&
        timestamp <= nowMs + 5 * 60 * 1000 &&
        nowMs - timestamp <= NEWS_WINDOW_MS;
    });
  }

  function calculateRadarSignals(marketData, newsItems, nowMs) {
    const now = Number.isFinite(nowMs) ? nowMs : Date.now();
    const updatedAt = marketData && marketData.updated_at ? Date.parse(marketData.updated_at) : NaN;
    const quotesFresh = Number.isFinite(updatedAt) &&
      updatedAt <= now + 5 * 60 * 1000 && now - updatedAt <= PRICE_STALE_MS;
    const quotes = Array.isArray(marketData && marketData.quotes) ? marketData.quotes : [];
    const stocks = marketData && marketData.stocks && typeof marketData.stocks === "object"
      ? marketData.stocks : {};
    const newsByTicker = new Map();

    recentNews(Array.isArray(newsItems) ? newsItems : [], now)
      .sort((a, b) => {
        const impact = (b.impact_level === "high" ? 1 : 0) - (a.impact_level === "high" ? 1 : 0);
        return impact || Date.parse(b.published || b.fetched_at) - Date.parse(a.published || a.fetched_at);
      })
      .forEach(item => {
        if (!newsByTicker.has(item.ticker)) newsByTicker.set(item.ticker, item);
      });

    const signals = [];
    quotes.forEach(quote => {
      if (!quote || typeof quote.symbol !== "string") return;
      const ticker = quote.symbol;
      const events = [];
      let score = 0;
      const change = Number.isFinite(quote.change_percent) ? quote.change_percent : null;

      if (quotesFresh && change !== null && Math.abs(change) >= 2.5) {
        const points = Math.abs(change) >= 5 ? 50 : 35;
        score += points;
        events.push({
          type: "price", label: "ราคาเคลื่อนไหวเด่น",
          detail: (change > 0 ? "+" : "") + change.toFixed(2) + "%",
          points
        });
      }

      const ratio = quotesFresh ? volumeRatio(stocks[ticker]) : null;
      if (ratio !== null && ratio >= 2) {
        const points = ratio >= 3 ? 35 : 25;
        score += points;
        events.push({
          type: "volume", label: "ปริมาณซื้อขายสูง",
          detail: ratio.toFixed(1) + "x เทียบค่ากลาง 12 แท่งก่อนหน้า",
          points
        });
      }

      const article = newsByTicker.get(ticker);
      if (article) {
        const points = article.impact_level === "high" ? 30 : 15;
        score += points;
        events.push({
          type: "news",
          label: article.impact_level === "high" ? "ข่าวผลกระทบสูง" : "ข่าวน่าจับตา",
          detail: article.impact_source === "gemini" ? "ประเมินโดย Gemini" : "ประเมินจากกฎสำรอง",
          points
        });
      }

      if (!events.length) return;
      const cappedScore = Math.min(100, score);
      signals.push({
        ticker, score: cappedScore,
        severity: cappedScore >= 65 ? "high" : cappedScore >= 35 ? "medium" : "watch",
        changePercent: change, volumeRatio: ratio, events, news: article || null
      });
    });

    return signals.sort((a, b) => b.score - a.score || a.ticker.localeCompare(b.ticker));
  }

  const api = { calculateRadarSignals, volumeRatio };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.MarketRadar = api;
})(typeof window !== "undefined" ? window : null);
