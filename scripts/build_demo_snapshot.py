# scripts/build_demo_snapshot.py
"""
Builds the offline market-data snapshot that powers demo mode.

Pulls real data once from free, keyless sources (Yahoo Finance via yfinance and
the public Forex Factory weekly calendar feed) and writes it to app/demo_data/.
The running app never calls these sources; it only reads the files written here.

Usage (from the repo root):
    pip install -r scripts/requirements-snapshot.txt
    python scripts/build_demo_snapshot.py
"""
import gzip
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

OUT_DIR = Path(__file__).resolve().parent.parent / "app" / "demo_data"
SYMBOL_DIR = OUT_DIR / "symbols"

# App symbol -> Yahoo symbol. Stocks get full fundamentals; everything else is price-only.
STOCKS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "INTC", "NFLX",
    "CRM", "ORCL", "ADBE", "AVGO", "JPM", "BAC", "GS", "V", "MA", "BRK-B",
    "JNJ", "UNH", "PFE", "LLY", "MRK", "XOM", "CVX", "KO", "PEP", "WMT",
    "COST", "PG", "HD", "MCD", "NKE", "DIS", "BA", "CAT", "T", "VZ",
    "NEE", "O", "PLD", "LIN", "SHOP", "TD", "BP", "SAP", "TM", "SONY",
]
INDEXES = {"^GSPC": "^GSPC", "^IXIC": "^IXIC", "^DJI": "^DJI"}
CRYPTO = {s: s.replace("USD", "-USD") for s in ["BTCUSD", "ETHUSD", "XRPUSD", "LTCUSD", "BCHUSD", "ADAUSD", "SOLUSD"]}
FOREX = {s: f"{s}=X" for s in ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "AUDUSD", "NZDUSD", "USDCHF"]}
DISPLAY_NAMES = {
    "^GSPC": "S&P 500", "^IXIC": "NASDAQ Composite", "^DJI": "Dow Jones Industrial Average",
    "BTCUSD": "Bitcoin USD", "ETHUSD": "Ethereum USD", "XRPUSD": "XRP USD", "LTCUSD": "Litecoin USD",
    "BCHUSD": "Bitcoin Cash USD", "ADAUSD": "Cardano USD", "SOLUSD": "Solana USD",
    "EURUSD": "Euro / US Dollar", "GBPUSD": "British Pound / US Dollar", "USDJPY": "US Dollar / Japanese Yen",
    "USDCAD": "US Dollar / Canadian Dollar", "AUDUSD": "Australian Dollar / US Dollar",
    "NZDUSD": "New Zealand Dollar / US Dollar", "USDCHF": "US Dollar / Swiss Franc",
}

COUNTRY_CODES = {
    "United States": "US", "Canada": "CA", "United Kingdom": "GB", "Germany": "DE", "Japan": "JP",
}
CALENDAR_COUNTRIES = {
    "USD": "US", "EUR": "EU", "GBP": "UK", "JPY": "JP", "CAD": "CA", "AUD": "AU",
    "NZD": "NZ", "CHF": "CH", "CNY": "CN", "All": "Global",
}
RATING_LABELS = {
    "strong_buy": "Strong Buy", "buy": "Buy", "hold": "Hold",
    "underperform": "Sell", "sell": "Strong Sell",
}


def clean(value, digits=4):
    """Converts numpy/pandas scalars to JSON-safe Python values."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (int,)) and not isinstance(value, bool):
        return value
    try:
        f = float(value)
    except (TypeError, ValueError):
        return value
    if math.isinf(f):
        return None
    return round(f, digits)


def bars(df, fmt, price_digits):
    rows = []
    for ts, r in df.iterrows():
        if pd.isna(r["Close"]):
            continue
        rows.append([
            ts.strftime(fmt),
            clean(r["Open"], price_digits), clean(r["High"], price_digits),
            clean(r["Low"], price_digits), clean(r["Close"], price_digits),
            int(r["Volume"]) if not pd.isna(r["Volume"]) else 0,
        ])
    return rows


def statement_rows(df, fields):
    """Turns a yfinance statement (metrics x periods) into FMP-style records, newest first."""
    if df is None or df.empty:
        return []
    records = []
    for col in df.columns:
        rec = {"date": col.strftime("%Y-%m-%d")}
        for out_key, candidates in fields.items():
            rec[out_key] = None
            for name in candidates:
                if name in df.index and not pd.isna(df.at[name, col]):
                    rec[out_key] = clean(df.at[name, col], 2)
                    break
        if any(v is not None for k, v in rec.items() if k != "date"):
            records.append(rec)
    return records[:5]


def news_items(ticker, symbol):
    items = []
    for raw in ticker.news or []:
        c = raw.get("content", raw)
        url = (c.get("canonicalUrl") or {}).get("url") or (c.get("clickThroughUrl") or {}).get("url")
        pub = c.get("pubDate")
        if not (c.get("title") and url and pub):
            continue
        thumb = None
        resolutions = (c.get("thumbnail") or {}).get("resolutions") or []
        if resolutions:
            thumb = min(resolutions, key=lambda r: r.get("width", 9999)).get("url")
        published = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        items.append({
            "symbol": symbol,
            "title": c["title"],
            "text": c.get("summary") or "",
            "url": url,
            "site": (c.get("provider") or {}).get("displayName") or "Yahoo Finance",
            "image": thumb,
            "publishedDate": published.strftime("%Y-%m-%d %H:%M:%S"),
        })
    return items


def build_symbol(symbol, yahoo_symbol, kind):
    t = yf.Ticker(yahoo_symbol)
    price_digits = 5 if kind == "forex" else 2

    daily = t.history(period="10y", interval="1d", auto_adjust=False)
    if daily.empty or len(daily) < 2:
        raise RuntimeError("no daily history")
    hourly = t.history(period="60d", interval="60m", auto_adjust=False)

    last, prev = daily.iloc[-1], daily.iloc[-2]
    info = {}
    if kind in ("stock", "index"):
        try:
            info = t.info or {}
        except Exception as e:  # info is best-effort
            print(f"    info unavailable: {e}")

    change = float(last["Close"] - prev["Close"])
    year = daily[daily.index >= daily.index[-1] - pd.Timedelta(days=365)]
    quote = {
        "symbol": symbol,
        "name": DISPLAY_NAMES.get(symbol) or info.get("longName") or info.get("shortName") or symbol,
        "price": clean(last["Close"], price_digits),
        "change": clean(change, price_digits),
        "changesPercentage": clean(change / float(prev["Close"]) * 100, 4),
        "open": clean(last["Open"], price_digits),
        "previousClose": clean(prev["Close"], price_digits),
        "dayHigh": clean(last["High"], price_digits),
        "dayLow": clean(last["Low"], price_digits),
        "yearHigh": clean(year["High"].max(), price_digits),
        "yearLow": clean(year["Low"].min(), price_digits),
        "volume": int(last["Volume"]) if not pd.isna(last["Volume"]) else 0,
        "avgVolume": info.get("averageVolume") or int(daily["Volume"].tail(90).mean()),
        "marketCap": info.get("marketCap"),
        "pe": clean(info.get("trailingPE"), 2),
        "eps": clean(info.get("trailingEps"), 2),
        "exchange": info.get("exchange") or kind.upper(),
        "timestamp": daily.index[-1].strftime("%Y-%m-%d"),
    }

    record = {
        "symbol": symbol,
        "kind": kind,
        "quote": quote,
        "daily": bars(daily, "%Y-%m-%d", price_digits),
        "hourly": bars(hourly, "%Y-%m-%d %H:%M:%S", price_digits) if not hourly.empty else [],
    }

    if kind != "stock":
        return record

    record["profile"] = {
        "symbol": symbol,
        "companyName": quote["name"],
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "country": COUNTRY_CODES.get(info.get("country"), info.get("country")),
        "beta": clean(info.get("beta"), 3),
        "description": info.get("longBusinessSummary"),
        "website": info.get("website"),
        "exchange": info.get("exchange"),
        "currency": info.get("currency"),
        "mktCap": info.get("marketCap"),
        "price": quote["price"],
        # yfinance reports dividendYield already as a percentage (0.33 == 0.33%)
        "dividendYield": clean(info.get("dividendYield"), 2) or 0,
    }

    rec_key = info.get("recommendationKey")
    rec_mean = info.get("recommendationMean")
    record["rating"] = {
        "symbol": symbol,
        "date": quote["timestamp"],
        "ratingRecommendation": RATING_LABELS.get(rec_key),
        # Yahoo's mean runs 1 (strong buy) .. 5 (strong sell); flip it so higher is better.
        "ratingScore": clean(6 - rec_mean, 2) if rec_mean else None,
        "analystCount": info.get("numberOfAnalystOpinions"),
    } if rec_key in RATING_LABELS else {}

    record["income"] = statement_rows(t.income_stmt, {
        "revenue": ["Total Revenue", "Operating Revenue"],
        "grossProfit": ["Gross Profit"],
        "netIncome": ["Net Income", "Net Income Common Stockholders"],
        "eps": ["Diluted EPS", "Basic EPS"],
    })
    record["balance"] = statement_rows(t.balance_sheet, {
        "totalAssets": ["Total Assets"],
        "totalLiabilities": ["Total Liabilities Net Minority Interest"],
        "totalStockholdersEquity": ["Stockholders Equity", "Common Stock Equity"],
    })

    earnings = []
    try:
        ed = t.earnings_dates
        if ed is not None:
            for ts, r in ed.iterrows():
                earnings.append({
                    "symbol": symbol,
                    "date": ts.strftime("%Y-%m-%d"),
                    "eps": clean(r.get("Reported EPS"), 2),
                    "epsEstimated": clean(r.get("EPS Estimate"), 2),
                })
    except Exception as e:
        print(f"    earnings unavailable: {e}")
    record["earnings"] = earnings[:8]

    try:
        record["news"] = news_items(t, symbol)
    except Exception as e:
        print(f"    news unavailable: {e}")
        record["news"] = []
    return record


def build_calendar():
    try:
        resp = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json", timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"Economic calendar unavailable: {e}")
        return []
    events = []
    for e in resp.json():
        when = pd.Timestamp(e["date"]).tz_convert("US/Eastern")
        events.append({
            "event": e["title"],
            "date": when.strftime("%Y-%m-%d %H:%M:%S"),
            "country": CALENDAR_COUNTRIES.get(e["country"], e["country"]),
            "impact": e["impact"] if e["impact"] in ("High", "Medium", "Low") else "Low",
            "estimate": e.get("forecast") or None,
            "previous": e.get("previous") or None,
        })
    return events


def build_index(calendar):
    """Writes index.json: the small, always-loaded part of the snapshot (quotes, profiles,
    ratings, news, earnings). Price history stays in the per-symbol files."""
    index = {"symbols": {}, "news": []}
    for path in sorted(SYMBOL_DIR.glob("*.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            record = json.load(f)
        index["symbols"][record["symbol"]] = {
            "kind": record["kind"],
            "quote": record["quote"],
            "profile": record.get("profile"),
            "rating": record.get("rating") or {},
            "earnings": record.get("earnings") or [],
        }
        index["news"] += record.get("news") or []
    if not index["symbols"]:
        sys.exit("No symbol files found; index not written.")

    # The same story is often tagged to several tickers; keep the first copy.
    seen, news = set(), []
    for article in sorted(index["news"], key=lambda a: a["publishedDate"], reverse=True):
        if article["url"] not in seen:
            seen.add(article["url"])
            news.append(article)
    index["news"] = news

    index["as_of"] = max(v["quote"]["timestamp"] for v in index["symbols"].values() if v["kind"] == "stock")
    index["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    index["economic_calendar"] = calendar

    with open(OUT_DIR / "index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, separators=(",", ":"))
    return index


def main():
    SYMBOL_DIR.mkdir(parents=True, exist_ok=True)
    universe = [(s, s, "stock") for s in STOCKS]
    universe += [(s, y, "index") for s, y in INDEXES.items()]
    universe += [(s, y, "crypto") for s, y in CRYPTO.items()]
    universe += [(s, y, "forex") for s, y in FOREX.items()]

    failures = []
    if "--index-only" not in sys.argv:
        for symbol, yahoo_symbol, kind in universe:
            print(f"Fetching {symbol} ({yahoo_symbol})...")
            try:
                record = build_symbol(symbol, yahoo_symbol, kind)
            except Exception as e:
                print(f"    FAILED: {e}")
                failures.append(symbol)
                continue
            with gzip.open(SYMBOL_DIR / f"{symbol}.json.gz", "wt", encoding="utf-8") as f:
                json.dump(record, f, separators=(",", ":"))
            time.sleep(0.5)  # be polite to Yahoo

    index = build_index(build_calendar())
    print(f"\nSnapshot as of {index['as_of']}: {len(index['symbols'])} symbols written to {OUT_DIR}")
    if failures:
        print(f"Failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
