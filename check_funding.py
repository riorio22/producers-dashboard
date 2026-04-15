#!/usr/bin/env python3
"""
check_funding.py
Fetches each funding institution's page, hashes the relevant content,
and compares to the previous hash stored in funding_status.json.
If anything changed, it flags it for manual review.
"""

import json
import hashlib
import re
import time
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError

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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ProducersDeskBot/1.0; deadline-checker)"
}

# Patterns that suggest date content — we extract these to make
# the hash sensitive to date changes but not to nav/cookie banners etc.
DATE_PATTERNS = [
    r'\b\d{1,2}\.\d{1,2}\.\d{4}\b',          # 15.01.2026
    r'\b\d{4}-\d{2}-\d{2}\b',                 # 2026-01-15
    r'\b(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+\d{4}\b',
    r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b',
    r'\bEinreichfrist\b',
    r'\bDeadline\b',
    r'\bSitzung\b',
    r'\bAntragsfrist\b',
]
DATE_RE = re.compile('|'.join(DATE_PATTERNS), re.IGNORECASE)


def extract_date_content(html_bytes):
    """Strip HTML tags, then extract only lines/sentences containing date-like content."""
    text = html_bytes.decode("utf-8", errors="replace")
    # Remove script/style blocks
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>',  ' ', text, flags=re.DOTALL | re.IGNORECASE)
    # Strip HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Normalise whitespace
    text = re.sub(r'\s+', ' ', text)

    # Keep only sentences/fragments that contain date-related content
    fragments = []
    for sentence in re.split(r'[.!?\n]', text):
        if DATE_RE.search(sentence):
            fragments.append(sentence.strip())

    return ' | '.join(fragments)


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def load_previous(path="funding_status.json"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def main():
    print(f"\n{'='*50}")
    print(f"check_funding.py — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*50}\n")

    previous = load_previous()
    results  = {}
    changed  = []
    errors   = []

    for page in FUNDING_PAGES:
        pid = page["id"]
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
            time.sleep(1)

        except URLError as e:
            print(f"  ✗  {page['institution']:20s}  {page['label']:40s}  URLError: {e.reason}")
            errors.append({"id": pid, "error": str(e.reason)})
        except Exception as e:
            print(f"  ✗  {page['institution']:20s}  {page['label']:40s}  Error: {e}")
            errors.append({"id": pid, "error": str(e)})

    # Write updated status
    with open("funding_status.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Write human-readable report
    report = {
        "checked_at":     datetime.now(timezone.utc).isoformat(),
        "total_checked":  len(results),
        "changed_count":  len(changed),
        "error_count":    len(errors),
        "changed_pages":  [{"institution": p["institution"], "label": p["label"], "url": p["url"]} for p in changed],
        "errors":         errors,
        "all_ok":         len(changed) == 0 and len(errors) == 0,
    }

    with open("funding_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n{'─'*50}")
    if changed:
        print(f"⚠️  {len(changed)} page(s) CHANGED — review manually:")
        for p in changed:
            print(f"   → {p['institution']}: {p['url']}")
    else:
        print("✓  No changes detected.")

    if errors:
        print(f"⚠️  {len(errors)} page(s) could not be fetched.")

    print(f"✓  Results saved to funding_status.json + funding_report.json")


if __name__ == "__main__":
    main()
