import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

def summarize_with_deepseek(messages: list[str]) -> str:
    prompt = (
        "请将以下用户消息整理成简明扼要的摘要，用于给群主参考：\n\n" +
        "\n".join(messages) +
        "\n\n请用条理清晰的中文总结关键信息，不必复述无关内容。"
    )
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    response = requests.post(
        "https://api.deepseek.com/v1/chat/completions",
        json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}]
        },
        headers=headers,
        timeout=20
    )
    return response.json()["choices"][0]["message"]["content"]

user_messages = {}

async def forward_and_summarize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    username = user.username or "（无用户名）"
    text = update.message.text or "[非文字消息]"

    if uid not in user_messages:
        user_messages[uid] = []
    user_messages[uid].append(text)
    user_messages[uid] = user_messages[uid][-5:]

    summary = summarize_with_deepseek(user_messages[uid])

    forward_text = f"📩 来自用户: @{username}\n🆔 用户ID: {uid}\n" +                    f"🗣 原始消息：\n" + "\n".join(user_messages[uid]) + "\n\n" +                    f"🧠 Deepseek整理摘要：\n{summary}"

    await context.bot.send_message(chat_id=OWNER_ID, text=forward_text)

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), forward_and_summarize))
    print("TgRentalBot with Deepseek is running...")
    app.run_polling()
