import os
import asyncio
from typing import Dict, List

from openai import OpenAI
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

# ----------------------
# Environment
# ----------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OWNER_ID_ENV = os.getenv("OWNER_ID")

if not BOT_TOKEN or not OPENAI_API_KEY or not OWNER_ID_ENV:
    raise ValueError("Missing required environment variables: BOT_TOKEN / OPENAI_API_KEY / OWNER_ID")

try:
    OWNER_ID = int(OWNER_ID_ENV)
except Exception:
    raise ValueError("OWNER_ID must be an integer user id, not @username.")

# ----------------------
# OpenAI client
# ----------------------
client = OpenAI(api_key=OPENAI_API_KEY)

# Default model and chat mode
current_model: str = "gpt-5-mini"
# False = forward-only mode (/start); True = chat mode (/chat)
chat_mode: bool = False

# Keyword watch list (group)
KEYWORDS: List[str] = ["Netflix", "YouTube", "shared", "rent", "group", "上车", "合租"]

# Cache last messages per user for summary (group)
user_messages: Dict[int, List[str]] = {}

# ----------------------
# System prompt
# ----------------------
SYSTEM_PROMPT = (
    "你是一个风格独特的 AI 助手，说话有点拽，风趣但不低俗，"
    "中文为主，偶尔夹杂英文。你擅长用文艺、哲理、调皮的语言回答问题，"
    "不走寻常路，拒绝废话，回答要简洁有力，偶尔带点诗意或黑色幽默。"
    "别太端着，也别太舔。"
)

# ----------------------
# Helpers
# ----------------------
async def ask_gpt(prompt: str, model: str) -> str:
    """Call OpenAI chat completion using the new SDK in a thread."""
    def _run():
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        # New SDK returns .message.content
        return resp.choices[0].message.content.strip()

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        return f"❌ Error from GPT: {e}"


def build_lines_header(title: str, username: str, uid: int) -> str:
    lines = [
        title,
        f"👤 From: @{username}" if username != "NoUsername" else f"👤 From: (no username)",
        f"🆔 User ID: {uid}",
    ]
    return "\n".join(lines)


# ----------------------
# Commands
# ----------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global chat_mode
    chat_mode = False
    lines = [
        "🔔 已切换到 *只转发模式*",        "📌 私聊消息将转发给管理员，不调用 GPT",        f"📦 当前模型：{current_model}",
    ]
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global chat_mode
    chat_mode = True
    lines = [
        "💬 已切换到 *聊天模式*",        "📌 私聊将调用 GPT 回复（群聊仍会关键词监听并转发）",        f"📦 当前模型：{current_model}",
    ]
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_model
    allowed = ["gpt-5-mini", "gpt-5", "gpt-5-pro"]
    if context.args:
        model_choice = context.args[0]
        if model_choice in allowed:
            current_model = model_choice
            await update.message.reply_text(f"✅ Model switched to: {current_model}")
        else:
            await update.message.reply_text("❌ Invalid model. Allowed: " + ", ".join(allowed))
    else:
        await update.message.reply_text(f"ℹ️ Current model: {current_model}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode_text = "聊天模式" if chat_mode else "只转发模式"
    lines = [
        f"📊 当前模式：{mode_text}",
        f"📦 当前模型：{current_model}",
    ]
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ I'm alive")


# ----------------------
# Message handler
# ----------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    user = update.effective_user
    username = user.username or "NoUsername"
    uid = user.id
    chat_type = message.chat.type
    text = message.text or "[non-text message]"

    # Private chat
    if chat_type == "private":
        if chat_mode:
            # Chat mode: call GPT
            reply = await ask_gpt(text, current_model)
            await message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)
        else:
            # Forward-only mode: forward private DM to OWNER
            header = build_lines_header("📬 *Private DM*", username, uid)
            forward_text = "\n\n".join([header, f"💬 Message:\n{text}"])
            await context.bot.send_message(chat_id=OWNER_ID, text=forward_text, parse_mode=ParseMode.MARKDOWN)
            await message.reply_text("✅ 已转发你的消息给管理员。", parse_mode=ParseMode.MARKDOWN)
        return

    # Group chat: keyword detection + owner summary forward
    triggered = any(k.lower() in text.lower() for k in KEYWORDS)
    if triggered:
        # keep last 5 messages for this user
        msgs = user_messages.setdefault(uid, [])
        msgs.append(text)
        user_messages[uid] = msgs[-5:]

        # Build summary prompt (single-line string + join, avoid f-string multiline issues)
        summary_prompt = (
            "Please summarize the following user messages into concise, useful points for the group owner. "
            "Focus on any keyword-related content.\n\n"
            + "\n".join(user_messages[uid])
        )
        summary = await ask_gpt(summary_prompt, current_model)

        owner_header = build_lines_header("📩 *Group Trigger*", username, uid)
        owner_body = "\n\n".join([
            owner_header,
            "🗣 Recent Messages:\n" + "\n".join(user_messages[uid]),
            "🧠 Summary by GPT:\n" + summary,
        ])
        await context.bot.send_message(chat_id=OWNER_ID, text=owner_body, parse_mode=ParseMode.MARKDOWN)

        # notify user in group
        await message.reply_text(f"🔔 Hey @{username}, your message triggered a keyword alert!", parse_mode=ParseMode.MARKDOWN)


# ----------------------
# Entrypoint
# ----------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("chat", cmd_chat))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("ping", cmd_ping))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("TgRentalBot loaded. Mode=Forward-only, Model=gpt-5-mini")  # default
    app.run_polling()


if __name__ == "__main__":
    main()
