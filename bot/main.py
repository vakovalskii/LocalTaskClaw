"""LocalClaw Telegram Bot — single-user, owner only."""

import asyncio
import logging
import os
import httpx
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction

CORE_URL = os.environ.get("CORE_URL", "http://core:8000")
API_SECRET = os.environ.get("API_SECRET", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

logging.basicConfig(
    format="%(asctime)s [bot] %(levelname)s %(message)s",
    level=logging.INFO,
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bot")


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if API_SECRET:
        h["X-Api-Key"] = API_SECRET
    return h


def _is_owner(update: Update) -> bool:
    if not OWNER_ID:
        return True  # No owner set — allow all (not recommended)
    uid = update.effective_user.id if update.effective_user else None
    return uid == OWNER_ID


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    await update.message.reply_text(
        "👋 LocalClaw запущен!\n\nПросто пиши — я твой личный агент.\n\n"
        "Команды:\n/clear — сбросить историю\n/help — помощь"
    )


async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    chat_id = update.effective_chat.id
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(f"{CORE_URL}/clear", json={"chat_id": chat_id}, headers=_headers())
    await update.message.reply_text("🗑️ История очищена")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    await update.message.reply_text(
        "🤖 *LocalClaw* — твой личный AI-агент\n\n"
        "Умею:\n"
        "• Запускать команды в рабочем пространстве\n"
        "• Искать в интернете\n"
        "• Читать и создавать файлы\n"
        "• Помнить важное между сессиями\n"
        "• Выполнять задачи по расписанию\n\n"
        "/clear — сбросить историю разговора\n"
        "/help — эта справка",
        parse_mode="Markdown",
    )


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return

    message = update.message
    if not message or not message.text:
        return

    chat_id = update.effective_chat.id
    text = message.text.strip()

    log.info(f"Message from {update.effective_user.id}: {text[:80]}")

    # Show typing indicator
    await ctx.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f"{CORE_URL}/chat",
                json={"message": text, "chat_id": chat_id},
                headers=_headers(),
            )
            resp.raise_for_status()
            data = resp.json()

        reply = data.get("text", "").strip()
        if not reply:
            reply = "🤔 Агент не вернул ответ"

        # Split long messages (Telegram limit: 4096 chars)
        for chunk in _split_message(reply, 4000):
            await message.reply_text(chunk)

    except httpx.TimeoutException:
        await message.reply_text("⏱️ Таймаут — задача заняла слишком много времени")
    except Exception as e:
        log.error(f"Core error: {e}")
        await message.reply_text(f"❌ Ошибка: {e}")


def _split_message(text: str, max_len: int) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Try to split at newline
        split_at = text.rfind("\n", 0, max_len)
        if split_at < max_len // 2:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages — acknowledge for now."""
    if not _is_owner(update):
        return
    await update.message.reply_text("📷 Получил фото. Vision ещё не подключён в этой версии.")


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not set")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    await app.bot.set_my_commands([
        BotCommand("clear", "Сбросить историю разговора"),
        BotCommand("help", "Помощь"),
    ])

    log.info(f"Bot started, owner_id={OWNER_ID}")

    # run_polling has event loop issues on Python 3.14 — use manual lifecycle
    async with app:
        await app.updater.start_polling(drop_pending_updates=True)
        await app.start()
        log.info("Polling... (Ctrl+C to stop)")
        # Keep running until interrupted
        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            await app.updater.stop()
            await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
