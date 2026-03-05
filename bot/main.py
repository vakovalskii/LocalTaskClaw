"""LocalTaskClaw Telegram Bot — single-user, owner only, with streaming."""

import asyncio
import logging
import os
import time
import json
import httpx
from telegram import Update, BotCommand, Message
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction
from telegram.error import BadRequest

# Load env file if ENV_FILE is set (LaunchAgent / systemd pass path this way)
_env_file = os.environ.get("ENV_FILE", "")
if _env_file and os.path.isfile(_env_file):
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

CORE_URL = os.environ.get("CORE_URL", "http://core:8000")
API_SECRET = os.environ.get("API_SECRET", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Streaming config
STREAM_THROTTLE_S = 0.8   # min seconds between editMessageText calls
DRAFT_THROTTLE_S = 0.3    # min seconds between sendMessageDraft calls (faster, no rate limit)
MAX_MSG_LEN = 4000         # Telegram limit is 4096

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
        return True
    uid = update.effective_user.id if update.effective_user else None
    return uid == OWNER_ID


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    await update.message.reply_text(
        "👋 LocalTaskClaw is running!\n\nJust type — I'm your personal agent.\n\n"
        "Commands:\n/clear — reset history\n/help — help"
    )


async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    chat_id = update.effective_chat.id
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(f"{CORE_URL}/clear", json={"chat_id": chat_id}, headers=_headers())
    await update.message.reply_text("🗑️ History cleared")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    await update.message.reply_text(
        "🤖 *LocalTaskClaw* — your personal AI agent\n\n"
        "I can:\n"
        "• Run commands in the workspace\n"
        "• Search the internet\n"
        "• Read and create files\n"
        "• Remember important things between sessions\n"
        "• Execute tasks on a schedule\n\n"
        "/clear — reset conversation history\n"
        "/help — this help message",
        parse_mode="Markdown",
    )


async def _stream_reply(
    chat_id: int,
    reply_to_msg_id: int,
    text: str,
    bot,
) -> None:
    """
    Stream a reply using SSE from /chat?stream=true.

    Strategy:
    1. Send placeholder message immediately
    2. Read SSE stream, accumulate text
    3. Use sendMessageDraft for live preview (Bot API 9.3+, fast throttle)
    4. On [DONE] — do final editMessageText with full content
    5. If too long — split into multiple messages
    """
    # Send placeholder
    sent_msg: Message = await bot.send_message(
        chat_id=chat_id,
        text="⏳",
        reply_to_message_id=reply_to_msg_id,
    )

    accumulated = ""
    last_draft_at = 0.0
    last_edit_at = 0.0
    tool_events: list[str] = []

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream(
                "POST",
                f"{CORE_URL}/chat",
                json={"message": text, "chat_id": chat_id, "stream": True},
                headers=_headers(),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload == "[DONE]":
                        break

                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue

                    etype = event.get("type", "")

                    if etype == "text":
                        accumulated += event.get("text", "")
                        now = time.monotonic()

                        # Try sendMessageDraft first (Bot API 9.3+ live preview)
                        if now - last_draft_at >= DRAFT_THROTTLE_S:
                            preview = accumulated[:MAX_MSG_LEN]
                            try:
                                await bot.send_message_draft(
                                    chat_id=chat_id,
                                    text=preview or "...",
                                    reply_to_message_id=reply_to_msg_id,
                                )
                                last_draft_at = now
                                log.debug(f"Draft sent: {len(preview)} chars")
                            except Exception as draft_err:
                                log.info(f"sendMessageDraft unavailable ({draft_err}), using editMessageText")
                                # Fallback: edit placeholder
                                if now - last_edit_at >= STREAM_THROTTLE_S and preview:
                                    try:
                                        await bot.edit_message_text(
                                            chat_id=chat_id,
                                            message_id=sent_msg.message_id,
                                            text=preview,
                                            parse_mode="Markdown",
                                        )
                                        last_edit_at = now
                                    except BadRequest:
                                        try:
                                            await bot.edit_message_text(
                                                chat_id=chat_id,
                                                message_id=sent_msg.message_id,
                                                text=preview,
                                            )
                                            last_edit_at = now
                                        except BadRequest:
                                            pass

                    elif etype == "tool_start":
                        name = event.get("name", "")
                        tool_events.append(f"🔧 {name}")

                    elif etype == "tool_done":
                        name = event.get("name", "")
                        ok = event.get("success", True)
                        icon = "✅" if ok else "❌"
                        # Update last tool marker in list
                        for i in range(len(tool_events) - 1, -1, -1):
                            if tool_events[i].endswith(name):
                                tool_events[i] = f"{icon} {name}"
                                break

    except httpx.TimeoutException:
        accumulated = accumulated or "⏱️ Timeout"
    except Exception as e:
        log.error(f"Stream error: {e}")
        accumulated = accumulated or f"❌ Stream error: {e}"

    # Final: delete placeholder + send full reply (split if needed)
    if not accumulated:
        accumulated = "🤔 Agent returned no response"

    chunks = _split_message(accumulated, MAX_MSG_LEN)

    try:
        await bot.delete_message(chat_id=chat_id, message_id=sent_msg.message_id)
    except Exception:
        pass  # Already deleted or can't delete — fine

    for i, chunk in enumerate(chunks):
        reply_to = reply_to_msg_id if i == 0 else None
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                reply_to_message_id=reply_to,
                parse_mode="Markdown",
            )
        except BadRequest:
            # Markdown parse failed (e.g. unmatched backticks) — send as plain text
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    reply_to_message_id=reply_to,
                )
            except Exception as e:
                log.error(f"Send chunk error: {e}")
        except Exception as e:
            log.error(f"Send chunk error: {e}")


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return

    message = update.message
    if not message or not message.text:
        return

    chat_id = update.effective_chat.id
    text = message.text.strip()

    log.info(f"Message from {update.effective_user.id}: {text[:80]}")

    await ctx.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    await _stream_reply(
        chat_id=chat_id,
        reply_to_msg_id=message.message_id,
        text=text,
        bot=ctx.bot,
    )


def _split_message(text: str, max_len: int) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
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
    await update.message.reply_text("📷 Photo received. Vision is not yet available in this version.")


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
        BotCommand("clear", "Reset conversation history"),
        BotCommand("help", "Help"),
    ])

    log.info(f"Bot started, owner_id={OWNER_ID}")

    # run_polling has event loop issues on Python 3.14 — use manual lifecycle
    async with app:
        await app.updater.start_polling(drop_pending_updates=True)
        await app.start()
        log.info("Polling... (Ctrl+C to stop)")
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
