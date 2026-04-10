---
date: 2026-04-10
type: learning
tags: [aiogram, telegram-bot, gateway]
source: "Gemini chat (link missing)"
---
[]()
# Aiogram Gateway Architecture

## Core Objects

Three central objects in the aiogram library:

- **Bot** — the main object that gives us the connection to the Telegram API, through which we send messages
- **Dispatcher** — listens to Telegram messages and processes them, using the Router to decide what to do with them
- **Router** — splits the logic so that not every message gets the same handling

## Message Flow (handle_message)

Everything is managed by `handle_message` in [[bot/gateway.py]].

1. Check if the message is text or something else — if not text, return a pre-formatted message saying the bot only supports text
2. Check if this chat already exists or if it's a new user who needs to enter a passphrase
3. If new user, the bot checks if the message sent is the passphrase and if it's the correct one — which probably didn't happen because the user likely sent "hi", so the bot asks them to enter the passphrase
4. Assuming the passphrase is correct, the registration flow we defined begins
5. After the registration flow completes, we exit and start forwarding the message to the LangGraph API

## Open Issues

- Session memory (known chat_id mapping) is managed in RAM ([[bot/gateway.py|SessionData]]). When the server goes down it gets wiped — needs to be migrated to Redis or similar persistent store

## Links

- [[bot/gateway.py]]
- [[docs/patterns/runtime-context.md]]
- [[docs/plans/phase3-auth-rls-telegram-gateway.md]]
- [[commit_logs/2026-03-13_14-30-00_feat-auth-rls-telegram-gateway.md]]
