"""Daily closes for every company and the STOXX Europe 600, from Yahoo Finance.

Abnormal return = stock return minus the STOXX Europe 600 return on the same day
(market-adjusted, beta of one). Size is measured in units of the stock's own
abnormal-return volatility over the previous 60 trading days, so a 2% move counts
as big for Nestle and as noise for Rolls-Royce.
"""
import time

import pandas as pd
import yfinance as yf

from .common import PRICES, load_universe

MARKET = "^STOXX"
# Yahoo sometimes publishes the index close a day late; the iShares STOXX Europe 600 ETF
# (Xetra) fills any day the index is missing, so no stock-day is lost waiting for it.
MARKET_FALLBACK = "EXSA.DE"
VOL_WINDOW = 60


def main():
    tickers = [c["ticker"] for c in load_universe()]
    # One request per ticker: the bulk download often leaves out the latest close for
    # some exchanges (11 Nov 2026: missing for 33 of 42 series fifteen hours after the close).
    series, patched = {}, []
    for t in tickers + [MARKET, MARKET_FALLBACK]:
        try:
            h = yf.Ticker(t).history(period="2y", interval="1d", auto_adjust=True)
        except Exception as e:
            print(f"  {t}: {e!r}")
            continue
        if h.empty:
            print(f"  {t}: no data")
            continue
        idx = h.index.tz_localize(None) if h.index.tz is not None else h.index
        daily = pd.Series(h["Close"].values, index=idx.normalize())
        # Yahoo can publish the daily bar a day or more late (11 Nov 2026: most European
        # stocks still missing the next morning). Fill missing recent days with the last
        # 30-minute bar of that day, which is normally the closing price.
        try:
            m = yf.Ticker(t).history(period="5d", interval="30m", auto_adjust=True)
            if not m.empty:
                local = m.index.tz_localize(None) if m.index.tz is None else m.index.tz_convert(m.index.tz).tz_localize(None)
                last_bar = pd.Series(m["Close"].values, index=local).groupby(local.normalize()).last()
                missing = last_bar[~last_bar.index.isin(daily.index)]
                if len(missing):
                    patched.append(f"{t}:{','.join(d.strftime('%m-%d') for d in missing.index)}")
                    daily = pd.concat([daily, missing]).sort_index()
        except Exception as e:
            print(f"  {t} intraday: {e!r}")
        series[t] = daily
        time.sleep(0.5)
    close = pd.DataFrame(series).sort_index()
    if patched:
        print("filled from intraday: " + " ".join(patched))
    # Drop today's row until every exchange has closed, so a live price is never used as a close
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    if now.hour < 21:
        close = close[close.index.strftime("%Y-%m-%d") < now.strftime("%Y-%m-%d")]
    PRICES.mkdir(parents=True, exist_ok=True)
    close.to_csv(PRICES / "close.csv")

    rets = close.pct_change(fill_method=None)
    mkt = rets[MARKET].fillna(rets[MARKET_FALLBACK])
    last = lambda col: close[col].dropna().index.max().strftime("%Y-%m-%d")
    print(f"last close: index {last(MARKET)}, ETF {last(MARKET_FALLBACK)}, "
          f"stocks {sorted({last(t) for t in tickers if t in close and close[t].notna().any()})}")
    rows = []
    for t in tickers:
        if t not in rets:
            continue
        s = close[t].dropna()
        r = s.pct_change().dropna()
        ar = (r - mkt.reindex(r.index)).dropna()
        sd = ar.rolling(VOL_WINDOW).std().shift(1)   # volatility known before the day
        fwd = ar[::-1].rolling(5).std()[::-1].shift(-1)  # next five days, for vol_up
        df = pd.DataFrame({"ticker": t, "ar": ar, "sd": sd, "fwd_sd": fwd})
        rows.append(df)
    out = pd.concat(rows).reset_index(names="date")
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out["z"] = out["ar"] / out["sd"]
    out.to_csv(PRICES / "abnormal.csv", index=False)
    print(f"abnormal returns: {len(out)} rows, last date {out['date'].max()}")


if __name__ == "__main__":
    main()
