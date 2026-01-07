import os
from datetime import datetime, timedelta, timezone

import feedparser
import requests
from dateutil import parser as dateparser
from openai import OpenAI

OPENAI_RSS = "https://openai.com/blog/rss.xml"
OPENAI_NEWS_FALLBACK = "https://openai.com/news"
DAYS_LOOKBACK = 7
MAX_ITEMS = 5

def must_env(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v

def parse_date_safe(s: str):
    try:
        return dateparser.parse(s)
    except Exception:
        return None

def now_utc():
    return datetime.now(timezone.utc)

def within_lookback(dt: datetime, days: int) -> bool:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= (now_utc() - timedelta(days=days))

def telegram_send(token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
        "parse_mode": "HTML",
    }
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()

def pick_candidates_from_rss():
    feed = feedparser.parse(OPENAI_RSS)
    entries = feed.entries or []

    candidates = []
    for e in entries:
        title = (e.get("title") or "").strip()
        link = (e.get("link") or "").strip()

        published = e.get("published") or e.get("updated") or ""
        dt = parse_date_safe(published) if published else None

        if not title or not link or not dt:
            continue
        if not within_lookback(dt, DAYS_LOOKBACK):
            continue

        summary = (e.get("summary") or "").strip()
        candidates.append({
            "title": title,
            "link": link,
            "dt": dt,
            "summary": summary[:1200],  # keep cost low
        })

    candidates.sort(key=lambda x: x["dt"], reverse=True)
    return candidates[:max(MAX_ITEMS, 1)]

def main():
    # Secrets via env vars (GitHub Actions)
    tg_token = must_env("TELEGRAM_BOT_TOKEN")
    tg_chat_id = must_env("TELEGRAM_CHAT_ID")
    openai_key = must_env("OPENAI_API_KEY")

    # 1) Collect candidates (RSS primary)
    candidates = pick_candidates_from_rss()

    # 2) If nothing recent, notify and exit (fallback is optional and can be added later)
    if not candidates:
        telegram_send(
            tg_token,
            tg_chat_id,
            "📡 <b>Radar IA (OpenAI)</b>\n\nNenhuma novidade relevante nos últimos 7 dias."
        )
        return

    # 3) Build prompt and summarize via OpenAI API (low cost)
    items_block = "\n\n".join(
        f"- Título: {c['title']}\n  Link: {c['link']}\n  Contexto (RSS): {c['summary']}"
        for c in candidates
    )

    system = (
        "Você é um editor técnico-executivo. Resuma notícias com objetividade, apenas fatos. "
        "Sem opinião. Em português. 4 a 6 linhas por notícia."
    )

    user = f"""Gere um boletim único com {len(candidates)} itens.

Regras:
- Cada item: TÍTULO em uma linha, depois 4–6 linhas de resumo.
- Incluir o link ao final do item.
- Não inventar detalhes: use apenas o contexto fornecido.
- Linguagem: PT-BR, factual.

Itens:
{items_block}
""".strip()

    client = OpenAI(api_key=openai_key)

    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_output_tokens=800,
    )

    text = resp.output_text.strip()

    header = f"📡 <b>Radar IA — OpenAI</b>\n🗓️ {datetime.now().strftime('%d/%m/%Y')}\n"
    final = header + "\n" + text

    # Telegram message limit is ~4096 chars; keep margin
    if len(final) > 3800:
        final = final[:3800] + "\n\n(boletim truncado por limite do Telegram)"

    telegram_send(tg_token, tg_chat_id, final)

if __name__ == "__main__":
    main()
