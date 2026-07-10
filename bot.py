import sqlite3
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ConversationHandler,
    filters, ContextTypes
)
import openai

# ============ الإعدادات (ضع مفتاح OpenAI هنا) ============
TOKEN = "8745236717:AAGjIacCY4SC2CtIFqDQAv5oZUEInFBg-Nk"   # توكنك الذي أرسلته
OPENAI_API_KEY = "YOUR_OPENAI_API_KEY"                     # ضع مفتاحك هنا

# أكواد التفعيل – غيّرها كما تشاء
VALID_CODES = {"MAGIC123", "VIP2026", "UNIQUE"}

# ============ قاعدة بيانات التفعيل ============
def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS activated (user_id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

def is_activated(user_id):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT 1 FROM activated WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def activate_user(user_id):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO activated VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

# ============ حالات المحادثة ============
WAITING_FOR_CODE = 1
CHATTING = 2

# ============ الذكاء الاصطناعي (OpenAI) ============
openai.api_key = OPENAI_API_KEY

async def ai_response(user_message, user_id):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "أنت مساعد شخصي فخم، خفيف الظل، تجيب بإتقان وبالعربية. اسمك 'كونسيرج'."},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"⚠️ حدث خطأ في الذكاء: {e}"

# ============ أوامر البوت ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_activated(user_id):
        await update.message.reply_text("👑 أهلاً بك سيدي! أنا في خدمتك. تفضل بأي سؤال أو طلب.")
        return CHATTING
    else:
        await update.message.reply_text(
            "🔐 *مرحباً بك في عالم كونسيرج*\n"
            "هذا البوت حصري ويتطلب كود تفعيل.\n"
            "أدخل الكود السحري الآن:",
            parse_mode="Markdown"
        )
        return WAITING_FOR_CODE

async def check_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if code in VALID_CODES:
        activate_user(update.effective_user.id)
        await update.message.reply_text(
            "✅ *تم التفعيل!*\n\n"
            "أنا الآن تحت أمرك. تستطيع أن تسألني أي شيء، أو تطلب مني تنفيذ مهمة.\n"
            "جرب أن تقول: 'ابحث عن أفضل مطاعم في دبي' أو 'ترجم لي هذه الجملة'.",
            parse_mode="Markdown"
        )
        return CHATTING
    else:
        await update.message.reply_text("❌ الكود غير صحيح. حاول مجدداً أو تواصل مع الدعم.")
        return WAITING_FOR_CODE

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_activated(user_id):
        await update.message.reply_text("🔒 الرجاء التفعيل أولاً باستخدام /start")
        return ConversationHandler.END

    user_text = update.message.text
    await update.message.chat.send_action(action="typing")
    reply = await ai_response(user_text, user_id)
    await update.message.reply_text(reply)
    return CHATTING

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚪 خرجت من وضع الدردشة. للعودة اكتب /start")
    return ConversationHandler.END

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_activated(update.effective_user.id):
        await update.message.reply_text("🔒 الرجاء التفعيل أولاً.")
        return
    query = " ".join(context.args) if context.args else None
    if not query:
        await update.message.reply_text("⚠️ استخدم: /search <كلمة البحث>")
        return
    await update.message.reply_text(f"🔍 جاري البحث عن '{query}'...\n(قم بتوصيل Google API هنا)")

async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_activated(update.effective_user.id):
        await update.message.reply_text("🔒 الرجاء التفعيل أولاً.")
        return
    city = " ".join(context.args) if context.args else "دمشق"
    await update.message.reply_text(f"🌤️ الطقس في {city}: مشمس 25°م (بيانات وهمية للعرض)")

# ============ التشغيل ============
def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_FOR_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_code)],
            CHATTING: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("weather", weather_command))

    print("🚀 كونسيرج الفخم يعمل الآن...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
