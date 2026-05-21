"""
AI News -> Hebrew -> Telegram channel publisher.

Reads a list of RSS feeds (feeds.yaml), translates and summarizes new items into
Hebrew using the Gemini free tier, and posts them to a Telegram channel.

State of "already-posted" items is kept in seen.json and committed back to the
repo by the GitHub Actions workflow.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
from pathlib import Path

import feedparser
import google.generativeai as genai
import requests
import yaml

# ---------- config ----------

FEEDS_FILE = Path(__file__).parent / "feeds.yaml"
SEEN_FILE = Path(__file__).parent / "seen.json"

MAX_ITEMS_PER_RUN = int(os.getenv("MAX_ITEMS_PER_RUN", "5"))
MAX_AGE_HOURS = int(os.getenv("MAX_AGE_HOURS", "48"))

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT = os.environ["TELEGRAM_CHAT_ID"]  # like "@yourchannel" or "-100..."
GEMINI_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

genai.configure(api_key=GEMINI_KEY)
_model = genai.GenerativeModel(GEMINI_MODEL)


# ---------- state ----------

def load_seen() -> set[str]:
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_seen(seen: set[str]) -> None:
    # keep only the most recent ~2000 entries so the file stays small
    bounded = sorted(seen)[-2000:]
    SEEN_FILE.write_text(
        json.dumps(bounded, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def item_id(entry) -> str:
    base = entry.get("id") or entry.get("link") or entry.get("title", "")
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


# ---------- fetch ----------

def strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def fetch_new_items(seen: set[str]) -> list[dict]:
    feeds = yaml.safe_load(FEEDS_FILE.read_text(encoding="utf-8"))["feeds"]
    cutoff = time.time() - MAX_AGE_HOURS * 3600
    new: list[dict] = []
    for f in feeds:
        try:
            parsed = feedparser.parse(f["url"])
        except Exception as e:
            print(f"[feed-error] {f['url']}: {e}")
            continue
        for entry in parsed.entries:
            iid = item_id(entry)
            if iid in seen:
                continue
            published = 0.0
            if entry.get("published_parsed"):
                published = time.mktime(entry.published_parsed)
            elif entry.get("updated_parsed"):
                published = time.mktime(entry.updated_parsed)
            if published and published < cutoff:
                continue
            new.append(
                {
                    "id": iid,
                    "title": (entry.get("title") or "").strip(),
                    "link": (entry.get("link") or "").strip(),
                    "summary": strip_html(
                        entry.get("summary") or entry.get("description") or ""
                    ),
                    "source": f.get("name") or parsed.feed.get("title") or "",
                    "published_ts": published or time.time(),
                }
            )
    new.sort(key=lambda x: x["published_ts"], reverse=True)
    return new[:MAX_ITEMS_PER_RUN]


# ---------- translate ----------

PROMPT = """כתוב פוסט קצר וזורם לערוץ טלגרם בעברית על הכתבה הבאה.

כותרת מקור: {title}
תוכן: {summary}
מקור: {source}

הנחיות:
- כתוב בעברית בלבד.
- סגנון מקצועי, ברור וזורם, מתאים לערוץ טלגרם.
- אל תכניס קישורים או האשטגים — אלה יתווספו אוטומטית.
- בלי הקדמות ובלי הסברים, רק התוכן עצמו.

החזר JSON בלבד עם שני שדות:
- "title_he": כותרת בעברית, שורה אחת, ללא תווי # או *.
- "body_he": 2-3 משפטים בעברית. מותר להתחיל באמוג'י אחד אם מתאים.
"""


def translate(item: dict) -> dict | None:
    prompt = PROMPT.format(
        title=item["title"],
        summary=(item["summary"] or "")[:1500],
        source=item["source"],
    )
    try:
        resp = _model.generate_content(
            prompt,
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.4,
                "max_output_tokens": 600,
            },
        )
        text = (resp.text or "").strip()
        # strip code fences if the model added them despite mime hint
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text).rstrip("`").strip()
        data = json.loads(text)
        title_he = (data.get("title_he") or "").strip()
        body_he = (data.get("body_he") or "").strip()
        if not title_he or not body_he:
            return None
        return {"title_he": title_he, "body_he": body_he}
    except Exception as e:
        print(f"[translate-error] {item.get('title','')[:80]}: {e}")
        return None


# ---------- post ----------

def post_to_telegram(item: dict, he: dict) -> bool:
    title = html.escape(he["title_he"])
    body = html.escape(he["body_he"])
    source = html.escape(item["source"])
    link = html.escape(item["link"], quote=True)

    msg = (
        f"🤖 <b>{title}</b>\n\n"
        f"{body}\n\n"
        f'🔗 <a href="{link}">המקור: {source}</a>\n\n'
        f"#AI #בינה_מלאכותית"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT,
                "text": msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=30,
        )
    except Exception as e:
        print(f"[telegram-error] network: {e}")
        return False
    if r.status_code != 200:
        print(f"[telegram-error] {r.status_code}: {r.text[:300]}")
        return False
    return True


# ---------- main ----------

def main() -> None:
    seen = load_seen()
    print(f"loaded {len(seen)} seen ids")

    items = fetch_new_items(seen)
    print(f"found {len(items)} candidate items")

    posted = 0
    for item in items:
        he = translate(item)
        if not he:
            # Transient failure (quota, rate limit, network). Don't mark seen —
            # let the next run try again. MAX_AGE_HOURS will eventually evict
            # any permanently broken item from the candidate list.
            continue
        if post_to_telegram(item, he):
            seen.add(item["id"])
            posted += 1
            time.sleep(2)  # be polite to Telegram

    save_seen(seen)
    print(f"posted {posted} items")


if __name__ == "__main__":
    main()
