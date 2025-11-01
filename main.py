import os
import asyncio
import html
import logging
from typing import Dict, List, Optional

from openai import OpenAI
from telegram import Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

# ============================================================================
# Configuration
# ============================================================================

# Tokens/keys are read from environment variables.
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Optional: comma-separated chat IDs to receive forwarded private DMs.
# Example: FORWARD_TO="-1001234567890,123456789"
FORWARD_TO_RAW = os.environ.get("FORWARD_TO", "").strip()
FORWARD_TO: List[int] = []
if FORWARD_TO_RAW:
    for _id in FORWARD_TO_RAW.split(","):
        _id = _id.strip()
        if not _id:
            continue
        try:
            FORWARD_TO.append(int(_id))
        except ValueError:
            # Ignore invalid values (only integers are valid Telegram chat IDs).
            pass

# Default OpenAI model (can be changed at runtime via /model command).
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-mini")

# In-memory settings per chat.
CHAT_MODE: Dict[int, str] = {}          # chat_id -> "forward" | "chat"
MODEL_PER_CHAT: Dict[int, str] = {}     # chat_id -> model string

# Lazily-created OpenAI client (avoids crash on import when key is missing).
_client: Optional[OpenAI] = None

# System prompt must be English as requested.
SYSTEM_PROMPT = (
    "You are a helpful assistant inside a Telegram bot. "
    "Be concise, factual, and reply in the user's language. "
    "When asked for analysis, explain briefly and clearly."
)

# Logging setup.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("TgRentalBot")


# ============================================================================
# OpenAI helpers
# ============================================================================

def get_client() -> OpenAI:
    """Return a singleton OpenAI client (OpenAI SDK >= 1.x)."""
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def get_model(chat_id: int) -> str:
    """Get the chosen model for a chat; fall back to default."""
    return MODEL_PER_CHAT.get(chat_id, DEFAULT_MODEL)


def set_mode(chat_id: int, mode: str) -> None:
    """Set mode for a chat. Allowed values: 'forward' or 'chat'."""
    CHAT_MODE[chat_id] = mode


def get_mode(chat_id: int) -> str:
    """Get mode for a chat. Default is 'forward' to keep forwarding behavior."""
    return CHAT_MODE.get(chat_id, "forward")


def _extract_choice_content(resp) -> str:
    """
    Return assistant text from the first choice.
    Supports both OpenAI 1.x object style and 0.x dict style for extra safety.
    """
    try:
        # New SDK (>=1.x): strong-typed objects.
        return resp.choices[0].message.content
    except AttributeError:
        # Old SDK (<=0.28): dictionary access.
        return resp["choices"][0]["message"]["content"]


async def ask_gpt(prompt: str, model: str) -> str:
    """
    Query OpenAI Chat Completions in a worker thread.
    Returns assistant text, or a short error string if something fails.
    """
    def _call_api() -> str:
        client = get_client()
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        return _extract_choice_content(resp).strip()

    try:
        return await asyncio.to_thread(_call_api)
    except Exception as e:
        # Keep error compact for Telegram UI.
        return f"❌ Error from GPT: {type(e).__name__}: {e}"


# ============================================================================
# Telegram command handlers
# ============================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show a quick help and current state."""
    chat_id = update.effective_chat.id
    msg = (
        "✅ Bot is running.\n"
        f"• Mode: <b>{html.escape(get_mode(chat_id))}</b>\n"
        f"• Model: <b>{html.escape(get_model(chat_id))}</b>\n\n"
        "Commands:\n"
        "/chat – switch to Chat mode (GPT replies in private chats)\n"
        "/forward – switch to Forward-only mode\n"
        "/model &lt;name&gt; – set OpenAI model\n"
        "/status – show current mode/model\n"
        "/ping – health check"
    )
    await update.effective_chat.send_message(msg, parse_mode=ParseMode.HTML)


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Simple liveness probe."""
    await update.effective_chat.send_message("✅ I'm alive")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Report current mode and model."""
    chat_id = update.effective_chat.id
    await update.effective_chat.send_message(
        f"📦 Current mode: <b>{html.escape(get_mode(chat_id))}</b>\n"
        f"🧠 Current model: <b>{html.escape(get_model(chat_id))}</b>",
        parse_mode=ParseMode.HTML
    )


async def cmd_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Switch to Chat mode (GPT replies in private chats)."""
    set_mode(update.effective_chat.id, "chat")
    await update.effective_chat.send_message(
        "💬 Switched to <b>Chat mode</b>. "
        "Send a message in private chat and I will reply with GPT.",
        parse_mode=ParseMode.HTML
    )


async def cmd_forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Switch to Forward-only mode."""
    set_mode(update.effective_chat.id, "forward")
    await update.effective_chat.send_message(
        "📨 Switched to <b>Forward-only mode</b>. "
        "Private messages will be forwarded when configured.",
        parse_mode=ParseMode.HTML
    )


async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set OpenAI model for this chat."""
    chat_id = update.effective_chat.id
    if not context.args:
        await update.effective_chat.send_message(
            "Usage: /model <name>\nExample: /model gpt-5-mini"
        )
        return
    MODEL_PER_CHAT[chat_id] = context.args[0]
    await update.effective_chat.send_message(
        f"🧠 Model set to <b>{html.escape(context.args[0])}</b>.",
        parse_mode=ParseMode.HTML
    )


# ============================================================================
# Forwarding helpers (kept minimal to preserve the basic forwarding feature)
# ============================================================================

def _format_private_forward(update: Update) -> str:
    """
    Build a readable message for forwarding private DMs.
    Only text content is handled here to keep behavior minimal.
    """
    user = update.effective_user
    text = update.effective_message.text or ""
    name = (user.full_name or "").strip()
    username = f"@{user.username}" if user and user.username else "(no username)"
    uid = user.id if user else 0

    body = (
        "📬 <b>Private DM</b>\n"
        f"👤 From: <b>{html.escape(name)}</b> {html.escape(username)}\n"
        f"🆔 User ID: <code>{uid}</code>\n\n"
        "💭 Message:\n"
        f"{html.escape(text)}"
    )
    return body


async def forward_if_needed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Forward private messages to the configured targets. If FORWARD_TO is empty,
    this function silently does nothing.
    """
    if not FORWARD_TO:
        return

    chat = update.effective_chat
    if chat.type == ChatType.PRIVATE:
        message = _format_private_forward(update)
        for target in FORWARD_TO:
            # Avoid echoing back into the same chat.
            if target == chat.id:
                continue
            try:
                await context.bot.send_message(
                    chat_id=target,
                    text=message,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                log.warning("Forwarding to %s failed: %s", target, e)


# ============================================================================
# Unified message handler
# ============================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Route messages by current mode:
      - 'forward': only forward private DMs.
      - 'chat': in private chats, call GPT and reply; groups are ignored.
    """
    chat = update.effective_chat
    mode = get_mode(chat.id)

    # Always try forwarding private DMs if configured.
    await forward_if_needed(update, context)

    # Chat mode only responds in private chats.
    if mode != "chat" or chat.type != ChatType.PRIVATE:
        return

    text = update.effective_message.text or ""
    if not text.strip():
        return

    model = get_model(chat.id)
    reply = await ask_gpt(text, model=model)
    await update.effective_message.reply_text(reply)


# ============================================================================
# Application bootstrap
# ============================================================================

def main() -> None:
    """Start the Telegram bot with polling."""
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("chat", cmd_chat))
    app.add_handler(CommandHandler("forward", cmd_forward))
    app.add_handler(CommandHandler("model", cmd_model))

    # Non-command text messages
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    log.info("TgRentalBot started. Default mode=forward, model=%s", DEFAULT_MODEL)
    app.run_polling(drop_pending_updates=True, timeout=60)


if __name__ == "__main__":
    main()
