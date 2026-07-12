import logging
import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ========== المفاتيح ==========
TELEGRAM_TOKEN = "8745236717:AAGjIacCY4SC2CtIFqDQAv4oZUEInFBg-Nk"
GROQ_API_KEY = "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"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

conversations = {}
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

PERSONAS = {
    "🤖 افتراضي": "أنت مساعد ذكي ومفيد. أجب بوضوح وباللغة العربية.",
    "😂 مضحك": "أنت كوميدي ومضحك. أجب بطريقة مرحة وخفيفة، واستخدم النكت.",
    "👨‍🍳 شيف": "أنت شيف محترف. أجب عن أسئلة الطبخ والوصفات والمكونات.",
    "💻 مبرمج": "أنت خبير برمجة. أجب عن أسئلة الكود والتقنية بدقة.",
    "🧠 طبيب نفسي": "أنت طبيب نفسي. استمع جيداً وأجب بتعاطف وحكمة.",
    "📚 معلم": "أنت معلم شرح. أجب بطريقة تعليمية بسيطة وواضحة."
}

def get_main_keyboard():
    buttons = [
        [KeyboardButton("🤖 افتراضي"), KeyboardButton("😂 مضحك")],
        [KeyboardButton("👨‍🍳 شيف"), KeyboardButton("💻 مبرمج")],
        [KeyboardButton("🧠 طبيب نفسي"), KeyboardButton("📚 معلم")],
        [KeyboardButton("🗑 مسح الذاكرة")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

async def start(update, context):
    uid = update.effective_user.id
    conversations[uid] = {"persona": PERSONAS["🤖 افتراضي"], "history": []}
    await update.message.reply_text("🌟 أهلاً بك! اختر شخصية أو اكتب رسالتك.", reply_markup=get_main_keyboard())

async def handle_message(update, context):
    uid = update.effective_user.id
    text = update.message.text

    if text in PERSONAS:
        conversations[uid] = {"persona": PERSONAS[text], "history": []}
        await update.message.reply_text(f"✅ تم تغيير الشخصية إلى: {text}", reply_markup=get_main_keyboard())
        return

    if text == "🗑 مسح الذاكرة":
        p = conversations.get(uid, {}).get("persona", PERSONAS["🤖 افتراضي"])
        conversations[uid] = {"persona": p, "history": []}
        await update.message.reply_text("🧹 تم مسح الذاكرة.", reply_markup=get_main_keyboard())
        return

    if uid not in conversations:
        conversations[uid] = {"persona": PERSONAS["🤖 افتراضي"], "history": []}

    data = conversations[uid]
    msgs = [{"role": "system", "content": data["persona"]}]
    for h in data["history"][-10:]:
        msgs.append({"role": "user", "content": h["user"]})
        msgs.append({"role": "assistant", "content": h["bot"]})
    msgs.append({"role": "user", "content": text})

    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        r = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": "llama3-8b-8192", "messages": msgs, "temperature": 0.7, "max_tokens": 1024},
            timeout=30
        )
        r.raise_for_status()
        reply = r.json()["choices"][0]["message"]["content"]
        data["history"].append({"user": text, "bot": reply})
        if len(data["history"]) > 50:
            data["history"] = data["history"][-50:]
        await update.message.reply_text(reply, reply_markup=get_main_keyboard())
    except Exception as e:
        await update.message.reply_text(f"⚠️ خطأ: {e}", reply_markup=get_main_keyboard())

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ البوت شغال...")
    app.run_polling()

if __name__ == "__main__":
    main()
