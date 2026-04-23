#!/usr/bin/env python3
"""
fetch_news.py
Fetches all RSS feeds and writes articles to news.json.
Run by GitHub Actions daily.
"""

import json
import time
import hashlib
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError
import xml.etree.ElementTree as ET

RSS_FEEDS = [
    # ── Top News ──────────────────────────────────────────────────────────────
    {"id": "variety_film",     "name": "Variety",              "url": "https://variety.com/v/film/feed/",                          "tab": "news"},
    {"id": "variety_tv",       "name": "Variety TV",           "url": "https://variety.com/v/tv/feed/",                            "tab": "news"},
    {"id": "deadline_film",    "name": "Deadline",             "url": "https://deadline.com/v/film/feed/",                         "tab": "news"},
    {"id": "deadline_tv",      "name": "Deadline TV",          "url": "https://deadline.com/v/tv/feed/",                           "tab": "news"},
    {"id": "thr_film",         "name": "THR",                  "url": "https://www.hollywoodreporter.com/c/movies/feed/",           "tab": "news"},
    {"id": "thr_tv",           "name": "THR TV",               "url": "https://www.hollywoodreporter.com/c/tv/feed/",               "tab": "news"},
    {"id": "indiewire_film",   "name": "IndieWire",            "url": "https://www.indiewire.com/t/film/feed/",                     "tab": "news"},
    {"id": "indiewire_tv",     "name": "IndieWire TV",         "url": "https://www.indiewire.com/t/tv/feed/",                      "tab": "news"},
    # ── Awards ────────────────────────────────────────────────────────────────
    {"id": "variety_cont",     "name": "Variety Contenders",   "url": "https://variety.com/e/contenders/feed/",                    "tab": "awards"},
    {"id": "thr_awards",       "name": "THR Awards",           "url": "https://www.hollywoodreporter.com/t/awards/feed/",           "tab": "awards"},
    {"id": "indiewire_awards", "name": "IndieWire Awards",     "url": "https://www.indiewire.com/c/awards/feed/",                  "tab": "awards"},
    # ── Industry ──────────────────────────────────────────────────────────────
    {"id": "screen_main",      "name": "Screen Daily",         "url": "https://www.screendaily.com/45202.rss",                     "tab": "industry"},
    {"id": "screen_prod",      "name": "Screen Daily Production","url": "https://www.screendaily.com/rss/production.rss",           "tab": "industry"},
    {"id": "screen_distrib",   "name": "Screen Daily Distribution","url": "https://www.screendaily.com/rss/distribution.rss",      "tab": "industry"},
    {"id": "screen_fund",      "name": "Screen Daily Funding", "url": "https://www.screendaily.com/rss/funding.rss",               "tab": "industry"},
    {"id": "screen_stream",    "name": "Screen Daily Streaming","url": "https://www.screendaily.com/rss/streaming.rss",            "tab": "industry"},
    # ── German & European ─────────────────────────────────────────────────────
    {"id": "cineuropa",        "name": "Cineuropa",            "url": "https://cineuropa.org/rss/en/",                             "tab": "german"},
    {"id": "dwdl_all",         "name": "DWDL",                 "url": "https://www.dwdl.de/rss/allethemen.xml",                    "tab": "german"},
    {"id": "dwdl_nachrichten", "name": "DWDL Nachrichten",     "url": "https://www.dwdl.de/rss/nachrichten.xml",                   "tab": "german"},
    {"id": "dwdl_magazin",     "name": "DWDL Magazin",         "url": "https://www.dwdl.de/rss/magazin.xml",                       "tab": "german"},
    {"id": "dwdl_interviews",  "name": "DWDL Interviews",      "url": "https://www.dwdl.de/rss/interviews.xml",                    "tab": "german"},
    # ── Festivals ─────────────────────────────────────────────────────────────
    {"id": "variety_fest",     "name": "Variety Festivals",    "url": "https://variety.com/v/film/festivals/feed/",                "tab": "festivals"},
    {"id": "screen_fest",      "name": "Screen Daily Festivals","url": "https://www.screendaily.com/rss/festivals.rss",            "tab": "festivals"},
    {"id": "deadline_fest",    "name": "Deadline Festivals",   "url": "https://deadline.com/tag/film-festivals/feed/",             "tab": "festivals"},
    {"id": "indiewire_fest",   "name": "IndieWire Festivals",  "url": "https://www.indiewire.com/t/film-festivals/feed/",          "tab": "festivals"},
    {"id": "cineuropa_fest",   "name": "Cineuropa Festivals",  "url": "https://cineuropa.org/rss/en/tag/?tag=festival",            "tab": "festivals"},
]

HEADERS = {
    "User-Agent": "ProducersDeskBot/1.0 (personal media dashboard; RSS reader; non-commercial)"
}

NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc":      "http://purl.org/dc/elements/1.1/",
    "atom":    "http://www.w3.org/2005/Atom",
}


def fetch_feed(feed):
    articles = []
    try:
        req = Request(feed["url"], headers=HEADERS)
        with urlopen(req, timeout=15) as resp:
            raw = resp.read()

        root = ET.fromstring(raw)

        # Handle both RSS and Atom
        channel = root.find("channel")
        if channel is None:
            # Try Atom
            items = root.findall("{http://www.w3.org/2005/Atom}entry")
            for item in items[:15]:
                title_el = item.find("{http://www.w3.org/2005/Atom}title")
                link_el  = item.find("{http://www.w3.org/2005/Atom}link")
                date_el  = item.find("{http://www.w3.org/2005/Atom}updated") or item.find("{http://www.w3.org/2005/Atom}published")
                title = title_el.text if title_el is not None else ""
                link  = link_el.get("href", "") if link_el is not None else ""
                date  = date_el.text if date_el is not None else ""
                if title and link:
                    articles.append({
                        "id":       hashlib.md5(link.encode()).hexdigest()[:10],
                        "title":    title.strip(),
                        "link":     link.strip(),
                        "pubDate":  date,
                        "source":   feed["name"],
                        "sourceId": feed["id"],
                        "tab":      feed["tab"],
                    })
        else:
            items = channel.findall("item")
            for item in items[:15]:
                title   = item.findtext("title", "").strip()
                link    = item.findtext("link", "").strip()
                pubdate = item.findtext("pubDate", "")
                if not title or not link:
                    continue
                articles.append({
                    "id":       hashlib.md5(link.encode()).hexdigest()[:10],
                    "title":    title,
                    "link":     link,
                    "pubDate":  pubdate,
                    "source":   feed["name"],
                    "sourceId": feed["id"],
                    "tab":      feed["tab"],
                })

        print(f"  ✓  {feed['name']:30s}  {len(articles)} articles")

    except URLError as e:
        print(f"  ✗  {feed['name']:30s}  URLError: {e.reason}")
    except ET.ParseError as e:
        print(f"  ✗  {feed['name']:30s}  ParseError: {e}")
    except Exception as e:
        print(f"  ✗  {feed['name']:30s}  Error: {e}")

    return articles


def main():
    print(f"\n{'='*55}")
    print(f"fetch_news.py — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*55}")

    all_articles = []
    seen_ids = set()

    for feed in RSS_FEEDS:
        articles = fetch_feed(feed)
        for a in articles:
            if a["id"] not in seen_ids:
                seen_ids.add(a["id"])
                all_articles.append(a)
        time.sleep(0.5)  # be polite to servers

    # Sort newest first (best-effort — pubDate formats vary)
    def sort_key(a):
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(a["pubDate"])
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    all_articles.sort(key=sort_key, reverse=True)

    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count":      len(all_articles),
        "articles":   all_articles,
    }

    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Wrote {len(all_articles)} articles to news.json")
    by_tab = {}
    for a in all_articles:
        by_tab.setdefault(a["tab"], 0)
        by_tab[a["tab"]] += 1
    for tab, count in sorted(by_tab.items()):
        print(f"   {tab:15s}  {count}")


if __name__ == "__main__":
    main()
