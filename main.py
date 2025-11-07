import os
import asyncio
import html
import logging
from typing import Dict, List, Optional, Tuple, Set

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
from telegram.error import RetryAfter, Forbidden

# ============================================================================
# Configuration
# ============================================================================

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Comma-separated chat IDs to receive forwarded private DMs.
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
            pass  # Ignore invalid chat IDs

# Comma-separated owner (admin) user IDs. Messages from these users are ignored
# for GPT replies and forwarding, but their replies to header messages are allowed.
OWNER_IDS_RAW = os.environ.get("OWNER_IDS", "").strip()
OWNER_IDS: Set[int] = set()
if OWNER_IDS_RAW:
    for _id in OWNER_IDS_RAW.split(","):
        _id = _id.strip()
        if not _id:
            continue
        try:
            OWNER_IDS.add(int(_id))
        except ValueError:
            pass  # Ignore invalid user IDs

DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-mini")

# Auth: only authorized users can use GPT chat (non-owners). Set a shared password.
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD", "").strip()
# In-memory authorized user id set (non-persistent). Consider persisting if needed.
AUTHORIZED_USERS: Set[int] = set()

# In-memory settings per chat.
CHAT_MODE: Dict[int, str] = {}          # chat_id -> "forward" | "chat"
MODEL_PER_CHAT: Dict[int, str] = {}     # chat_id -> model string

# Reply bridge map: (target_chat_id, forwarded_header_msg_id) -> original_user_id
REPLY_MAP: Dict[Tuple[int, int], int] = {}

# Lazily-created OpenAI client.
_client: Optional[OpenAI] = None

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
log = logging.getLogger("Wanatring-Yaoyu-Bot")


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


def is_owner_id(user_id: Optional[int]) -> bool:
    """Return True if the given Telegram user_id is configured as an owner/admin."""
    if user_id is None:
        return False
    return user_id in OWNER_IDS


def is_authorized_user(user_id: Optional[int]) -> bool:
    if user_id is None:
        return False
    # Owners are implicitly allowed for chat even without password
    if is_owner_id(user_id):
        return True
    return user_id in AUTHORIZED_USERS


def _extract_choice_content(resp) -> str:
    """Return assistant text from first choice (OpenAI 1.x or 0.x style)."""
    try:
        return resp.choices[0].message.content
    except AttributeError:
        return resp["choices"][0]["message"]["content"]


async def ask_gpt(prompt: str, model: str) -> str:
    """Call OpenAI Chat Completions in a worker thread."""
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
        return f"❌ Error from GPT: {type(e).__name__}: {e}"


# ============================================================================
# Telegram commands
# ============================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        "/ping – health check\n"
        "/auth &lt;password&gt; – authorize non-owners to use GPT chat\n\n"
        "💡 Reply bridge: Reply to the bot's forwarded header message in any chat to answer the original user.\n"
        "🔒 Owner policy: Owners can <b>chat with GPT</b> (private) and can <b>reply to forwarded headers</b> to message the original user.\n"
        "🔐 Non-owners must /auth before using GPT chat (to protect API key)."
    )
    await update.effective_chat.send_message(msg, parse_mode=ParseMode.HTML)


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_chat.send_message("✅ I'm alive")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await update.effective_chat.send_message(
        f"📦 Current mode: <b>{html.escape(get_mode(chat_id))}</b>\n"
        f"🧠 Current model: <b>{html.escape(get_model(chat_id))}</b>",
        parse_mode=ParseMode.HTML
    )


async def cmd_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    set_mode(update.effective_chat.id, "chat")
    await update.effective_chat.send_message(
        "💬 Switched to <b>Chat mode</b>. Send a message in private chat and I will reply with GPT.",
        parse_mode=ParseMode.HTML
    )


async def cmd_forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    set_mode(update.effective_chat.id, "forward")
    await update.effective_chat.send_message(
        "📨 Switched to <b>Forward-only mode</b>. Private messages will be forwarded when configured.",
        parse_mode=ParseMode.HTML
    )


async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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


async def cmd_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None:
        return

    if is_owner_id(user_id):
        await update.effective_chat.send_message("🔑 Owner detected: you already have access to chat.")
        return

    if not AUTH_PASSWORD:
        await update.effective_chat.send_message("❌ This bot requires no password right now. Please contact the owner if you think this is a mistake.")
        return

    if not context.args:
        await update.effective_chat.send_message("Usage: /auth <password>")
        return

    if context.args[0] == AUTH_PASSWORD:
        AUTHORIZED_USERS.add(user_id)
        await update.effective_chat.send_message("✅ Authorized. You can now chat with GPT in private.")
    else:
        await update.effective_chat.send_message("❌ Wrong password.")


# ============================================================================
# Forwarding + reply bridge
# ============================================================================

async def _safe_send(coro):
    """Run a Telegram API coroutine with gentle rate limiting & retry on 429."""
    try:
        return await coro
    except RetryAfter as e:
        await asyncio.sleep(int(getattr(e, "retry_after", 2)) + 1)
        return await coro


def _format_private_header(update: Update) -> str:
    """Header message that explains how to reply back to the original user."""
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
        f"{html.escape(text)}\n\n"
        "↩️ <i>Reply to this message to answer the user via the bot.</i>"
    )
    return body


async def forward_if_needed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Forward private messages to configured targets and create a reply bridge."""
    if not FORWARD_TO:
        return

    chat = update.effective_chat

    # Do not forward messages authored by owners/admins.
    user_id = update.effective_user.id if update.effective_user else None
    if is_owner_id(user_id):
        return

    if chat.type != ChatType.PRIVATE:
        return

    user_id = update.effective_user.id if update.effective_user else 0
    msg = update.effective_message
    header = _format_private_header(update)

    for target in FORWARD_TO:
        if target == chat.id:
            continue
        try:
            header_msg = await _safe_send(context.bot.send_message(
                chat_id=target,
                text=header,
                parse_mode=ParseMode.HTML
            ))
            if header_msg and getattr(header_msg, "message_id", None):
                REPLY_MAP[(target, header_msg.message_id)] = user_id

            if not msg.text:
                await _safe_send(context.bot.copy_message(
                    chat_id=target,
                    from_chat_id=chat.id,
                    message_id=msg.message_id
                ))
        except Forbidden as e:
            log.warning("Forward forbidden to %s: %s", target, e)
        except Exception as e:
            log.warning("Forward failed to %s: %s", target, e)


async def handle_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Deliver replies back to the original user.
    Works in ANY chat, including your private DM with the bot.
    """
    m = update.effective_message
    if not m or not m.reply_to_message:
        return


    key = (update.effective_chat.id, m.reply_to_message.message_id)
    user_id = REPLY_MAP.get(key)
    if not user_id:
        return  # not replying to a header we sent

    try:
        if m.text:
            await _safe_send(context.bot.send_message(chat_id=user_id, text=m.text))
        else:
            await _safe_send(context.bot.copy_message(
                chat_id=user_id,
                from_chat_id=update.effective_chat.id,
                message_id=m.message_id
            ))
    except Forbidden as e:
        await m.reply_text(f"❌ Cannot deliver: {e}")
    except Exception as e:
        await m.reply_text(f"❌ Delivery failed: {e}")


# ============================================================================
# Unified message handler
# ============================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat

    user_id = update.effective_user.id if update.effective_user else None
    mode = get_mode(chat.id)

    # Keep forwarding behavior (but forward_if_needed() already skips owners)
    await forward_if_needed(update, context)

    # GPT chat is only in private chats and only in chat mode
    if chat.type != ChatType.PRIVATE or mode != "chat":
        return

    # Authorization: owners are always allowed; others must be authorized
    if not is_authorized_user(user_id):
        if AUTH_PASSWORD:
            await update.effective_message.reply_text("🔐 Unauthorized. Use /auth <password> to enable GPT chat.")
        else:
            await update.effective_message.reply_text("🔐 GPT chat is restricted. Contact the owner for access.")
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
    app.add_handler(CommandHandler("auth", cmd_auth))

    # Replies to our header messages in ANY chat (group or private)
    app.add_handler(MessageHandler(filters.REPLY & filters.ALL, handle_reply))

    # Non-command text messages
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    log.info(
        "Wanatring·Yaoyu bot started. Default mode=forward, model=%s, owners=%s, auth_required=%s",
        DEFAULT_MODEL,
        sorted(list(OWNER_IDS)) if OWNER_IDS else [],
        bool(AUTH_PASSWORD),
    )
    app.run_polling(drop_pending_updates=True, timeout=60)


if __name__ == "__main__":
    main()
