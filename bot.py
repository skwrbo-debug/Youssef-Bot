from dotenv import load_dotenv
load_dotenv()

import os
import logging
import time
from collections import deque
from typing import Dict

import google.generativeai as genai
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ========== (1) الإعدادات ==========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    raise ValueError(
        "❌ التوكنات ناقصة!\n"
        "أنشئ ملف .env في نفس المجلد واكتب فيه:\n"
        "TELEGRAM_TOKEN=توكنك\n"
        "GEMINI_API_KEY=مفتاحك"
    )

genai.configure(api_key=GEMINI_API_KEY)

# ========== (2) الإعدادات العامة ==========
MAX_HISTORY = 10
MAX_TEXT_LEN = 4000
RATE_LIMIT_SEC = 2

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ========== (3) الشخصيات ==========
PERSONAS = {
    "🤖 افتراضي": "أنت مساعد ذكي ومفيد. أجب بوضوح وباللغة العربية.",
    "😂 مضحك": "أنت كوميدي ومضحك. أجب بطريقة مرحة وخفيفة، واستخدم النكت.",
    "👨‍🍳 شيف": "أنت شيف محترف. أجب عن أسئلة الطبخ والوصفات والمكونات.",
    "💻 مبرمج": "أنت خبير برمجة. أجب عن أسئلة الكود والتقنية بدقة.",
    "🧠 طبيب نفسي": "أنت طبيب نفسي. استمع جيداً وأجب بتعاطف وحكمة.",
    "📚 معلم": "أنت معلم شرح. أجب بطريقة تعليمية بسيطة وواضحة.",
}

# ========== (4) الجلسات ==========
class UserSession:
    __slots__ = ("persona", "history", "last_message_time")
    
    def __init__(self, persona: str):
        self.persona = persona
        self.history: deque = deque(maxlen=MAX_HISTORY)
        self.last_message_time: float = 0.0

conversations: Dict[int, UserSession] = {}

# ========== (5) لوحة المفاتيح ==========
def get_main_keyboard():
    buttons = [
        [KeyboardButton("🤖 افتراضي"), KeyboardButton("😂 مضحك")],
        [KeyboardButton("👨‍🍳 شيف"), KeyboardButton("💻 مبرمج")],
        [KeyboardButton("🧠 طبيب نفسي"), KeyboardButton("📚 معلم")],
        [KeyboardButton("🗑 مسح الذاكرة"), KeyboardButton("❓ مساعدة")],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# ========== (6) الأوامر ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversations[user_id] = UserSession(PERSONAS["🤖 افتراضي"])
    
    await update.message.reply_text(
        "🌟 *أهلاً بك في البوت الذكي!*\n\n"
        "أنا بوت متعدد الشخصيات يعمل بـ *Gemini AI*.\n"
        "• اختر شخصية من الأسفل\n"
        "• أو اكتب سؤالك مباشرة\n"
        "• استخدم *مسح الذاكرة* لبدء محادثة جديدة\n\n"
        "_ملاحظة: الذاكرة محدودة بآخر 10 رسائل._",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(),
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *كيفية الاستخدام:*\n\n"
        "1️⃣ اختر شخصية من الأزرار\n"
        "2️⃣ اكتب سؤالك أو أرسل صورة مع وصف\n"
        "3️⃣ البوت يتذكر السياق (آخر 10 رسائل)\n\n"
        "⚡ *الأوامر:*\n"
        "/start - بدء البوت\n"
        "/help - هذا المساعدة\n\n"
        "🧹 *مسح الذاكرة* - لمسح السياق الحالي"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

# ========== (7) معالجة الرسائل ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text or ""
    
    # --- Rate Limiting ---
    now = time.time()
    session = conversations.get(user_id)
    if session and (now - session.last_message_time) < RATE_LIMIT_SEC:
        await update.message.reply_text(
            "⏳ *بطّل شوي...* أرسل رسالة كل ثانيتين.",
            parse_mode="Markdown",
        )
        return
    
    # --- تغيير الشخصية ---
    if user_text in PERSONAS:
        conversations[user_id] = UserSession(PERSONAS[user_text])
        await update.message.reply_text(
            f"✅ تم تغيير الشخصية إلى: *{user_text}*",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(),
        )
        return
    
    # --- مسح الذاكرة ---
    if user_text == "🗑 مسح الذاكرة":
        persona = session.persona if session else PERSONAS["🤖 افتراضي"]
        conversations[user_id] = UserSession(persona)
        await update.message.reply_text("🧹 تم مسح الذاكرة.", reply_markup=get_main_keyboard())
        return
    
    # --- مساعدة ---
    if user_text == "❓ مساعدة":
        await help_cmd(update, context)
        return
    
    # --- التحقق من الطول ---
    if len(user_text) > MAX_TEXT_LEN:
        await update.message.reply_text(
            "⚠️ الرسالة طويلة جداً. اختصرها وأعد الإرسال.",
            reply_markup=get_main_keyboard(),
        )
        return
    
    # --- تهيئة الجلسة ---
    if user_id not in conversations:
        conversations[user_id] = UserSession(PERSONAS["🤖 افتراضي"])
    
    session = conversations[user_id]
    session.last_message_time = now
    
    # --- بناء المحادثة لـ Gemini (الذاكرة الفعلية) ---
    history_text = ""
    for turn in session.history:
        history_text += f"المستخدم: {turn['user']}\nأنت: {turn['bot']}\n\n"
    
    full_prompt = (
        f"التعليمات: {session.persona}\n\n"
        f"محادثة سابقة:\n{history_text}\n"
        f"المستخدم الآن: {user_text}\n\n"
        f"أجب الآن:"
    )
    
    # --- إرسال الطلب ---
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        chat = model.start_chat(history=[])
        response = chat.send_message(full_prompt)
        reply = response.text
        
        # حفظ في الذاكرة
        session.history.append({"user": user_text, "bot": reply})
        
        # تقسيم الرد الطويل
        if len(reply) > 4096:
            for i in range(0, len(reply), 4096):
                await update.message.reply_text(
                    reply[i:i+4096],
                    reply_markup=get_main_keyboard(),
                )
        else:
            await update.message.reply_text(reply, reply_markup=get_main_keyboard())
            
    except genai.types.BlockedPromptException:
        await update.message.reply_text(
            "🚫 تم حظر هذا الطلب لأسباب أمان. جرّب صياغة مختلفة.",
            reply_markup=get_main_keyboard(),
        )
    except Exception as e:
        logger.error(f"Error for user {user_id}: {e}")
        await update.message.reply_text(
            "⚠️ حدث خطأ تقني. جرّب مرة أخرى بعد لحظات.",
            reply_markup=get_main_keyboard(),
        )

# ========== (8) معالجة الصور ==========
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    caption = update.message.caption or "صفّ هذه الصورة أو حلّلها"
    
    if user_id not in conversations:
        conversations[user_id] = UserSession(PERSONAS["🤖 افتراضي"])
    
    session = conversations[user_id]
    
    # تحميل الصورة
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    try:
        response = model.generate_content([
            session.persona + "\n\n" + caption,
            {"mime_type": "image/jpeg", "data": bytes(image_bytes)}
        ])
        await update.message.reply_text(response.text, reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"Image error: {e}")
        await update.message.reply_text(
            "⚠️ تعذّر تحليل الصورة.",
            reply_markup=get_main_keyboard(),
        )

# ========== (9) التشغيل ==========
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("✅ البوت يعمل...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
