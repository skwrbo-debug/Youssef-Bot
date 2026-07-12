import os
import logging
import groq
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ========== (1) قراءة المفاتيح من متغيرات البيئة ==========
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# التحقق من وجود المفاتيح
if not TELEGRAM_TOKEN or not GROQ_API_KEY:
    raise ValueError("❌ ناقص متغيرات البيئة! شغل: export TELEGRAM_TOKEN=... && export GROQ_API_KEY=...")

# ============================================================

client = groq.Groq(api_key=GROQ_API_KEY)
conversations = {}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# الشخصيات
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversations[user_id] = {"persona": PERSONAS["🤖 افتراضي"], "history": []}
    await update.message.reply_text(
        "🌟 **أهلاً بك في البوت الأسطوري!**\n\n"
        "أنا بوت شامل بستخدم GROQ، أستطيع الرد على أي سؤال.\n"
        "اختر شخصية من الأسفل، أو اكتب رسالتك مباشرة.",
        reply_markup=get_main_keyboard()
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text

    if user_text in PERSONAS:
        conversations[user_id] = {"persona": PERSONAS[user_text], "history": []}
        await update.message.reply_text(
            f"✅ تم تغيير الشخصية إلى: {user_text}",
            reply_markup=get_main_keyboard()
        )
        return

    if user_text == "🗑 مسح الذاكرة":
        persona = conversations.get(user_id, {}).get("persona", PERSONAS["🤖 افتراضي"])
        conversations[user_id] = {"persona": persona, "history": []}
        await update.message.reply_text(
            "🧹 تم مسح الذاكرة.",
            reply_markup=get_main_keyboard()
        )
        return

    if user_id not in conversations:
        conversations[user_id] = {"persona": PERSONAS["🤖 افتراضي"], "history": []}

    user_data = conversations[user_id]

    messages = [{"role": "system", "content": user_data['persona']}]
    
    for entry in user_data["history"][-10:]:
        messages.append({"role": "user", "content": entry["user"]})
        messages.append({"role": "assistant", "content": entry["bot"]})
    
    messages.append({"role": "user", "content": user_text})

    try:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing"
        )

        chat_completion = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=messages,
            temperature=0.7,
            max_tokens=1024
        )

        reply = chat_completion.choices[0].message.content
        user_data["history"].append({"user": user_text, "bot": reply})
        
        if len(user_data["history"]) > 50:
            user_data["history"] = user_data["history"][-50:]

        await update.message.reply_text(reply, reply_markup=get_main_keyboard())

    except Exception as e:
        logging.error(f"Error: {e}")
        await update.message.reply_text(
            f"⚠️ صار خطأ: {str(e)}",
            reply_markup=get_main_keyboard()
        )

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ البوت شغال...")
    app.run_polling()

if __name__ == "__main__":
    main()
