import os
from telegram import Update, ParseMode
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from openai import OpenAI

TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

mode = {}

def start(update: Update, context: CallbackContext):
    mode[update.effective_chat.id] = "forward"
    update.message.reply_text("📨 Forwarding mode enabled.")

def chat(update: Update, context: CallbackContext):
    mode[update.effective_chat.id] = "chat"
    update.message.reply_text("💬 Chat mode enabled.")

def handle_message(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    text = update.message.text

    if mode.get(chat_id) == "chat":
        try:
            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": text}
                ]
            )
            reply_text = response.choices[0].message["content"]
            update.message.reply_text(reply_text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            update.message.reply_text(f"❌ Error: {e}")
    else:
        # Forward to owner
        header = "\n".join([
            f"👤 *Private DM*",
            f"From: `{update.effective_user.full_name}`",
            f"User ID: `{update.effective_user.id}`"
        ])
        context.bot.send_message(OWNER_ID, header + "\n\n" + text, parse_mode=ParseMode.MARKDOWN)

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("chat", chat))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    if not TOKEN or not OWNER_ID or not OPENAI_API_KEY:
        raise ValueError("Missing required environment variables.")
    main()
