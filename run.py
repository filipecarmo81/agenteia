import os
import sys
import textwrap
import requests
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from openai import OpenAI


RSS_URL_DEFAULT = "https://openai.com/blog/rss.xml"


def _get_text(elem, tag):
    child = elem.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def fetch_rss_items(rss_url: str, limit: int = 10):
    """
    Parseia RSS (XML) com biblioteca padrão.
    Retorna lista de itens com: title, link, published_dt, description.
    """
    r = requests.get(rss_url, timeout=30, headers={"User-Agent": "RadarIA/1.0"})
    r.raise_for_status()

    root = ET.fromstring(r.text)

    # RSS 2.0 típico: <rss><channel><item>...
    channel = root.find("channel")
    if channel is None:
        # Alguns feeds usam namespaces; tentar achar channel na marra
        channel = root.find(".//channel")
    if channel is None:
        return []

    items = []
    for item in channel.findall("item"):
        title = _get_text(item, "title")
        link = _get_text(item, "link")
        desc = _get_text(item, "description")
        pub = _get_text(item, "pubDate")

        published_dt = None
        if pub:
            try:
                published_dt = parsedate_to_datetime(pub)
            except Exception:
                published_dt = None

        if title and link:
            items.append(
                {
                    "title": title,
                    "link": link,
                    "published_dt": published_dt,
                    "description": desc,
                    "pub_raw": pub,
                }
            )

    # Ordena por data (mais recente primeiro). Itens sem data vão pro fim.
    items.sort(key=lambda x: (x["published_dt"] is None, x["published_dt"]), reverse=True)
    return items[:limit]


def build_prompt(items, topic_name: str):
    """
    Monta prompt para resumir 5 itens, PT-BR, 4–6 linhas, factual.
    """
    bullets = []
    for i, it in enumerate(items, start=1):
        dt = it["published_dt"].isoformat() if it["published_dt"] else (it["pub_raw"] or "sem data")
        bullets.append(
            f"{i}. Título: {it['title']}\n"
            f"   Data: {dt}\n"
            f"   Link: {it['link']}\n"
            f"   Trecho/descrição: {it['description'][:300]}"
        )

    joined = "\n\n".join(bullets)

    return f"""
Você é um curador de notícias de IA. Gere uma mensagem ÚNICA em português (PT-BR), objetiva, factual (sem opinião), com 5 notícias do tópico: "{topic_name}".

Regras:
- Cada notícia deve ter: título em negrito, 4–6 linhas de resumo (misto: o que aconteceu + por que importa), e o link.
- Ranqueie implicitamente considerando: Relevância, Data mais recente, Novidade, Impacto.
- Evite paywall. Se parecer paywall, apenas cite o título + link e explique em 1 linha que é paywall.
- Não invente fatos; use apenas o que está nos títulos/descrições fornecidos.

Itens coletados (RSS):
{joined}
""".strip()


def send_telegram_message(bot_token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    # Secrets/Vars esperados
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()

    # Config
    rss_url = os.environ.get("RSS_URL", RSS_URL_DEFAULT).strip()
    topic_name = os.environ.get("TOPIC_NAME", "Modelos de Linguagem & Foundation Models").strip()

    # MODELO: deixe configurável para evitar 403
    # Ex.: gpt-4o-mini, gpt-4o, ou outro que seu projeto tenha acesso
    openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()

    if not telegram_token or not telegram_chat_id:
        print("ERRO: TELEGRAM_BOT_TOKEN e/ou TELEGRAM_CHAT_ID não configurados.", file=sys.stderr)
        sys.exit(1)

    if not openai_key:
        print("ERRO: OPENAI_API_KEY não configurada.", file=sys.stderr)
        sys.exit(1)

    items = fetch_rss_items(rss_url, limit=10)
    if not items:
        send_telegram_message(
            telegram_token,
            telegram_chat_id,
            f"Radar IA: não consegui ler o RSS agora.\nFonte: {rss_url}",
        )
        return

    top5 = items[:5]
    prompt = build_prompt(top5, topic_name)

    client = OpenAI(api_key=openai_key)

    try:
        resp = client.responses.create(
            model=openai_model,
            input=prompt,
        )
        # SDK atual retorna texto agregado em output_text
        text = (resp.output_text or "").strip()
        if not text:
            raise RuntimeError("Resposta vazia do modelo.")
    except Exception as e:
        # Fallback: manda só títulos+links para não ficar sem entrega
        lines = [f"Radar IA (fallback) — não consegui resumir via OpenAI.\nMotivo: {type(e).__name__}\n"]
        for it in top5:
            lines.append(f"- {it['title']}\n  {it['link']}")
        text = "\n".join(lines)

    # Telegram tem limite ~4096 chars por msg. Se passar, corta.
    if len(text) > 3800:
        text = textwrap.shorten(text, width=3800, placeholder="\n\n(...)")

    send_telegram_message(telegram_token, telegram_chat_id, text)


if __name__ == "__main__":
    main()
