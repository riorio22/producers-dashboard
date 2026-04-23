#!/usr/bin/env python3
"""
check_funding.py
Checks German film funding pages for deadline changes.

Legal/ethical design principles:
- Honest User-Agent identifying this as a personal bot
- Checks robots.txt before fetching any page
- Runs weekly (Mondays only) not daily — funding deadlines change monthly at most
- 3-second crawl delay between requests to avoid server load
- Fetches only the minimal public deadline pages, never paywalled content
- Personal/non-commercial use only
"""

import json
import hashlib
import re
import time
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse

# ── Honest, identifiable User-Agent ──────────────────────────────────────────
# Identifying as a bot is both honest and more legally defensible in Germany.
# Anyone reading access logs can see what this is and why.
BOT_NAME    = "ProducersDeskBot"
BOT_VERSION = "1.0"
BOT_CONTACT = "personal-dashboard-bot"   # replace with your email if you like
USER_AGENT  = f"{BOT_NAME}/{BOT_VERSION} (personal media dashboard; non-commercial; {BOT_CONTACT})"

HEADERS = {"User-Agent": USER_AGENT}

# ── Crawl politeness ──────────────────────────────────────────────────────────
CRAWL_DELAY_SECONDS = 3   # wait between each page fetch

# ── Run schedule ─────────────────────────────────────────────────────────────
# This script is called daily by GitHub Actions, but actually fetches pages
# only on Mondays — reducing traffic by 6/7 while still catching monthly changes.
RUN_ONLY_ON_WEEKDAY = 0   # 0 = Monday; set to None to run every day

FUNDING_PAGES = [
    {
        "id":          "ffa_termine",
        "institution": "FFA",
        "label":       "Einreich- & Sitzungstermine 2026",
        "url":         "https://www.ffa.de/einreich-sitzungstermine.html",
        "hint":        "Jurybasierte Förderung, Produktionsförderung, Kinderfilm, Koproduktionsfonds",
    },
    {
        "id":          "fff_stoffe",
        "institution": "FFF Bayern",
        "label":       "Stoffentwicklung",
        "url":         "https://www.fff-bayern.de/foerderbereiche/stoffentwicklung/",
        "hint":        "Einreichfenster Langfilm & Serie",
    },
    {
        "id":          "fff_produktion",
        "institution": "FFF Bayern",
        "label":       "Produktion Kinofilm",
        "url":         "https://www.fff-bayern.de/foerderbereiche/produktion-kinofilm/",
        "hint":        "Einreichfenster Produktion",
    },
    {
        "id":          "fff_international",
        "institution": "FFF Bayern",
        "label":       "Internationale Kinofilme & Serien",
        "url":         "https://www.fff-bayern.de/foerderbereiche/internationale-kinofilme-und-serien/",
        "hint":        "Jederzeit möglich",
    },
    {
        "id":          "nrw_termine",
        "institution": "Filmstiftung NRW",
        "label":       "Einreichtermine",
        "url":         "https://www.filmstiftung.de/foerderung/servicecenter/einreichtermine/",
        "hint":        "Produktion & Stoffentwicklung",
    },
    {
        "id":          "moin_foerderung",
        "institution": "MOIN Hamburg/SH",
        "label":       "Förderung Übersicht",
        "url":         "https://moin-filmfoerderung.de/foerderung",
        "hint":        "NEST, High End, Director's Cut",
    },
    {
        "id":          "mfg_fristen",
        "institution": "MFG BW",
        "label":       "Einreichfristen",
        "url":         "https://www.mfg.de/service/einreichfristen/",
        "hint":        "Stoffentwicklung & Produktion",
    },
    {
        "id":          "medienboard_film",
        "institution": "Medienboard BB",
        "label":       "Förderung Film",
        "url":         "https://www.medienboard.de/foerderung/film",
        "hint":        "Stoff- & Projektentwicklung / Produktion",
    },
]

DATE_RE = re.compile(
    r'\b\d{1,2}\.\d{1,2}\.\d{4}\b'                     # 15.01.2026
    r'|\b\d{4}-\d{2}-\d{2}\b'                           # 2026-01-15
    r'|\b(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+\d{4}\b'
    r'|\b(Einreichfrist|Deadline|Sitzung|Antragsfrist|Einreichfenster)\b',
    re.IGNORECASE
)

# Cache robots.txt per domain so we only fetch it once per run
_robots_cache: dict = {}


def is_allowed(url: str) -> bool:
    """Return True if robots.txt permits our bot to fetch this URL."""
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in _robots_cache:
        rp = RobotFileParser()
        robots_url = f"{origin}/robots.txt"
        try:
            rp.set_url(robots_url)
            rp.read()
            _robots_cache[origin] = rp
            print(f"  ℹ  robots.txt read for {parsed.netloc}")
        except Exception as e:
            # If robots.txt can't be fetched, assume allowed (standard practice)
            print(f"  ℹ  robots.txt not found for {parsed.netloc} — assuming allowed ({e})")
            _robots_cache[origin] = None
    rp = _robots_cache[origin]
    if rp is None:
        return True
    allowed = rp.can_fetch(BOT_NAME, url)
    if not allowed:
        print(f"  ⛔  robots.txt DISALLOWS {url} for {BOT_NAME}")
    return allowed


def extract_date_content(html_bytes: bytes) -> str:
    """Strip HTML, keep only lines containing date/deadline keywords."""
    text = html_bytes.decode("utf-8", errors="replace")
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>',  ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    fragments = [s.strip() for s in re.split(r'[.!?\n]', text) if DATE_RE.search(s)]
    return ' | '.join(fragments)


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def load_previous(path="funding_status.json") -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def should_run_today() -> bool:
    if RUN_ONLY_ON_WEEKDAY is None:
        return True
    today = datetime.now(timezone.utc).weekday()
    if today != RUN_ONLY_ON_WEEKDAY:
        day_names = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        print(f"  ℹ  Skipping fetch today ({day_names[today]}) — runs on {day_names[RUN_ONLY_ON_WEEKDAY]}s only.")
        print(f"  ℹ  This reduces server traffic by ~85% vs daily crawling.")
        return False
    return True


def main():
    print(f"\n{'='*55}")
    print(f"check_funding.py — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"User-Agent: {USER_AGENT}")
    print(f"{'='*55}\n")

    previous = load_previous()

    # On non-run days, write a minimal status file so the dashboard
    # knows when the last real check was, without fetching anything.
    if not should_run_today():
        last_check = previous.get("_meta", {}).get("last_full_check", "never")
        report = {
            "checked_at":    datetime.now(timezone.utc).isoformat(),
            "skipped":       True,
            "last_full_check": last_check,
            "changed_count": 0,
            "changed_pages": [],
            "all_ok":        True,
        }
        with open("funding_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return

    results = {}
    changed = []
    errors  = []

    for page in FUNDING_PAGES:
        pid = page["id"]

        # 1. Check robots.txt first
        if not is_allowed(page["url"]):
            print(f"  ⛔  {page['institution']:20s}  {page['label']:40s}  SKIPPED (robots.txt)")
            errors.append({"id": pid, "error": "disallowed by robots.txt"})
            time.sleep(1)
            continue

        # 2. Fetch the page
        try:
            req = Request(page["url"], headers=HEADERS)
            with urlopen(req, timeout=20) as resp:
                raw = resp.read()

            content      = extract_date_content(raw)
            current_hash = hash_content(content)
            prev_entry   = previous.get(pid, {})
            prev_hash    = prev_entry.get("hash", "")

            status = "unchanged"
            if not prev_hash:
                status = "first_check"
            elif current_hash != prev_hash:
                status = "CHANGED"
                changed.append(page)

            results[pid] = {
                "institution": page["institution"],
                "label":       page["label"],
                "url":         page["url"],
                "hint":        page["hint"],
                "hash":        current_hash,
                "status":      status,
                "checked_at":  datetime.now(timezone.utc).isoformat(),
                "prev_hash":   prev_hash,
            }

            icon = "🔴" if status == "CHANGED" else ("🟡" if status == "first_check" else "🟢")
            print(f"  {icon}  {page['institution']:20s}  {page['label']:40s}  {status}")

        except URLError as e:
            print(f"  ✗  {page['institution']:20s}  {page['label']:40s}  URLError: {e.reason}")
            errors.append({"id": pid, "error": str(e.reason)})
        except Exception as e:
            print(f"  ✗  {page['institution']:20s}  {page['label']:40s}  Error: {e}")
            errors.append({"id": pid, "error": str(e)})

        # 3. Polite crawl delay between each page
        time.sleep(CRAWL_DELAY_SECONDS)

    # Persist results
    results["_meta"] = {"last_full_check": datetime.now(timezone.utc).isoformat()}
    with open("funding_status.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    report = {
        "checked_at":      datetime.now(timezone.utc).isoformat(),
        "skipped":         False,
        "last_full_check": datetime.now(timezone.utc).isoformat(),
        "total_checked":   len(results) - 1,   # exclude _meta
        "changed_count":   len(changed),
        "error_count":     len(errors),
        "changed_pages":   [{"institution": p["institution"], "label": p["label"], "url": p["url"]} for p in changed],
        "errors":          errors,
        "all_ok":          len(changed) == 0 and len(errors) == 0,
    }
    with open("funding_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n{'─'*55}")
    if changed:
        print(f"⚠️  {len(changed)} page(s) CHANGED — review manually:")
        for p in changed:
            print(f"   → {p['institution']}: {p['url']}")
    else:
        print("✓  No changes detected.")
    if errors:
        print(f"⚠️  {len(errors)} page(s) had errors or were blocked by robots.txt.")
    print(f"✓  Results saved to funding_status.json + funding_report.json")


if __name__ == "__main__":
    main()
