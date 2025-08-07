# TgRentalBot 🤖

A smart Telegram bot for subscription sharing groups. Supports keyword-based alerts and GPT-4o powered AI chat.

## ✨ Features

- 📢 Keyword alerts (e.g. "合租", "上车", "Netflix")
- 🤖 Private chat with GPT-4o (Markdown replies)
- ⚙️ Easy to deploy on Railway or any Python host
- 🌐 Keep-alive endpoint for UptimeRobot

## 🚀 Setup

### 1. Clone the repo

```bash
git clone https://github.com/Sifortonzh/TgRentalBot.git
cd TgRentalBot
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Create `.env` file

```env
BOT_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_openai_api_key
OWNER_ID=your_telegram_id
```

### 4. Run the bot

```bash
python main.py
```

## 📦 Deploy on Railway

1. Connect this repo to Railway
2. Add environment variables in Railway:
   - `BOT_TOKEN`
   - `OPENAI_API_KEY`
   - `OWNER_ID`
3. Enable UptimeRobot keep-alive ping (URL: `https://your-app.railway.app/ping`)

## 🧠 Powered by

- [OpenAI GPT-4o](https://platform.openai.com/docs/models/gpt-4o)
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)

## 👤 Author

[@lovekikiforever](https://t.me/lovekikiforever)  
https://github.com/Sifortonzh
