# TgRentalBot 🤖

一个为 Telegram 合租群设计的轻量级 Bot，支持自动转发成员消息并调用 Deepseek AI 整理内容，为群主提供清晰摘要反馈。

## ✨ 功能说明
- 📩 自动接收所有用户私聊消息
- 🔁 转发给群主（含用户名和用户ID）
- 🧠 使用 Deepseek 自动整理内容，输出「原文 + 摘要」
- 🔐 支持 Railway / Render 云部署

## 🧪 安装依赖
```
pip install -r requirements.txt
```

## 📦 环境变量（.env）
```env
BOT_TOKEN=你的Bot Token
OWNER_ID=你的 Telegram ID
DEEPSEEK_API_KEY=你的 Deepseek API Key
```

## 🚀 部署指南（Render / Railway）
详见 README 上文说明。支持搭配 UptimeRobot 保活。
