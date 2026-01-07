# Radar IA (OpenAI) — MVP

Este repositório roda um boletim de notícias da OpenAI via RSS e envia um resumo para o Telegram.

## O que faz (MVP)
- Lê `https://openai.com/blog/rss.xml`
- Filtra itens dos últimos 7 dias (até 5 itens)
- Resume via OpenAI API
- Envia 1 mensagem única no Telegram

## Como rodar na nuvem (gratuito)
Use GitHub Actions (já incluído).  
Depois de subir estes arquivos no seu GitHub:

1) Vá em **Settings → Secrets and variables → Actions**
2) Crie 3 secrets:
   - `OPENAI_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

3) Vá em **Actions → Radar IA (OpenAI) - Manual → Run workflow**

## Observações
- Não coloque tokens no código.
- Se o token do Telegram tiver vazado em prints, revogue no BotFather.
