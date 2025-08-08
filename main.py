import os
<<<<<<< HEAD
import asyncio
from openai import OpenAI
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters
=======
import openai
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
>>>>>>> 7b060b5041f71e7534763dedd73bb22015ba166b

# 环境变量
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

<<<<<<< HEAD
# 初始化 OpenAI 客户端
client = OpenAI(api_key=OPENAI_API_KEY)

# 默认模型
current_model = "gpt-5-mini"
=======
openai.api_key = OPENAI_API_KEY
>>>>>>> 7b060b5041f71e7534763dedd73bb22015ba166b

# 自定义 AI 助手风格
SYSTEM_PROMPT = (
    "你是一个风格独特的 AI 助手，说话有点拽，风趣但不低俗，"
    "中文为主，偶尔夹杂英文。你擅长用文艺、哲理、调皮的语言回答问题，"
    "不走寻常路，拒绝废话，回答要简洁有力，偶尔带点诗意或黑色幽默。"
    "别太端着，也别太舔。"
)

<<<<<<< HEAD
# GPT 调用函数（异步包装同步接口）
async def ask_gpt(prompt: str, model: str) -> str:
    def _run():
        resp = client.chat.completions.create(
            model=model,
=======
# GPT 调用函数
async def ask_gpt(prompt: str) -> str:
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
>>>>>>> 7b060b5041f71e7534763dedd73bb22015ba166b
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
        )
<<<<<<< HEAD
        return resp.choices[0].message.content.strip()

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        return f"❌ Error from GPT: {e}"

# 切换模型命令
async def set_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_model
    if context.args:
        model_choice = context.args[0]
        allowed = ["gpt-5-mini", "gpt-5", "gpt-5-pro"]
        if model_choice in allowed:
            current_model = model_choice
            await update.message.reply_text(f"✅ Model switched to: {current_model}")
        else:
            await update.message.reply_text(f"❌ Invalid model. Allowed: {', '.join(allowed)}")
    else:
        await update.message.reply_text(f"ℹ️ Current model: {current_model}")

=======
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"❌ Error from GPT: {e}"

>>>>>>> 7b060b5041f71e7534763dedd73bb22015ba166b
user_messages = {}
KEYWORDS = ["Netflix", "YouTube", "shared", "rent", "group", "上车", "合租"]

# 消息处理
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = update.effective_user
    chat_type = message.chat.type
    uid = user.id
    username = user.username or "NoUsername"
    text = message.text or "[non-text message]"

    # 私聊：AI 聊天
    if chat_type == "private":
<<<<<<< HEAD
        reply = await ask_gpt(text, current_model)
=======
        reply = await ask_gpt(text)
>>>>>>> 7b060b5041f71e7534763dedd73bb22015ba166b
        await message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)
        return

    # 群聊关键词监听 + 摘要转发
    triggered = any(keyword.lower() in text.lower() for keyword in KEYWORDS)
    if triggered:
        if uid not in user_messages:
            user_messages[uid] = []
        user_messages[uid].append(text)
        user_messages[uid] = user_messages[uid][-5:]

        prompt = "Please summarize the following user messages into concise, useful points for the group owner. Focus on any keyword-related content.\n\n" + "\n".join(user_messages[uid])
<<<<<<< HEAD
        summary = await ask_gpt(prompt, current_model)
=======
        summary = await ask_gpt(prompt)
>>>>>>> 7b060b5041f71e7534763dedd73bb22015ba166b

        forward_text = (
            f"📩 From: @{username}\n🆔 User ID: {uid}\n"
            f"🗣 Recent Messages:\n" + "\n".join(user_messages[uid]) + "\n\n"
            f"🧠 Summary by GPT:\n{summary}"
        )
        await context.bot.send_message(chat_id=OWNER_ID, text=forward_text)

        await message.reply_text(
            f"🔔 Hey @{username}, your message triggered a keyword alert!",
            parse_mode=ParseMode.MARKDOWN
        )

if __name__ == "__main__":
    if not BOT_TOKEN or not OPENAI_API_KEY:
        raise ValueError("Missing required environment variables.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
<<<<<<< HEAD
    app.add_handler(CommandHandler("model", set_model))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("TgRentalBot with GPT-5-mini is running...")
=======
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("TgRentalBot with GPT is running...")
>>>>>>> 7b060b5041f71e7534763dedd73bb22015ba166b
    app.run_polling()
