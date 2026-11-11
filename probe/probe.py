import time, json, requests, xml.etree.ElementTree as ET
import yfinance as yf
print("== yfinance news")
for t in ["ASML.AS", "BRBY.L", "CFR.SW", "NOVO-B.CO", "1913.HK"]:
    try:
        n = yf.Ticker(t).news or []
        print(t, len(n))
        for a in n[:3]:
            c = a.get("content", a)
            print("   ", c.get("pubDate") or c.get("providerPublishTime"), "|", (c.get("title") or "")[:90], "|", (c.get("provider") or {}).get("displayName") if isinstance(c.get("provider"), dict) else c.get("publisher"))
    except Exception as e:
        print(t, "ERROR", repr(e)[:200])
    time.sleep(2)
print("== google news rss")
for q in ['"ASML"', '"Burberry"', '"Richemont"']:
    try:
        r = requests.get("https://news.google.com/rss/search", params={"q": q + " when:1d", "hl": "en-GB", "gl": "GB", "ceid": "GB:en"}, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        items = ET.fromstring(r.content).findall(".//item")
        print(q, r.status_code, len(items))
        for it in items[:3]:
            print("   ", it.findtext("pubDate"), "|", it.findtext("title")[:90])
    except Exception as e:
        print(q, "ERROR", repr(e)[:200])
    time.sleep(2)
print("== gdelt single")
r = requests.get("https://api.gdeltproject.org/api/v2/doc/doc", params={"query": '"ASML" sourcelang:english', "mode": "artlist", "format": "json", "maxrecords": 5, "timespan": "8h"}, timeout=30)
print(r.status_code, r.text[:200])
