import os
import time
import requests
from collections import deque

import telebot

# ========== (1) الإعدادات ==========
TELEGRAM_TOKEN = "8745236717:AAGjIacCY4SC2CtIFqDQAv5oZUEInFBg-Nk"
OPENROUTER_KEY = "sk-or-v1-..."  # ← حط مفتاح OpenRouter هنا

bot = telebot.TeleBot(TELEGRAM_TOKEN)

conversations = {}

# ========== (2) الإعدادات العامة ==========
MAX_HISTORY = 10
RATE_LIMIT_SEC = 2

# ========== (3) الشخصيات ==========
PERSONAS = {
    "🤖 افتراضي": "أنت مساعد ذكي ومفيد. أجب بوضوح وباللغة العربية.",
    "😂 مضحك": "أنت كوميدي ومضحك. أجب بطريقة مرحة وخفيفة، واستخدم النكت.",
    "👨‍🍳 شيف": "أنت شيف محترف. أجب عن أسئلة الطبخ والوصفات والمكونات.",
    "💻 مبرمج": "أنت خبير برمجة. أجب عن أسئلة الكود والتقنية بدقة.",
    "🧠 طبيب نفسي": "أنت طبيب نفسي. استمع جيداً وأجب بتعاطف وحكمة.",
    "📚 معلم": "أنت معلم شرح. أجب بطريقة تعليمية بسيطة وواضحة.",
}

# ========== (4) لوحة المفاتيح ==========
def get_main_keyboard():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🤖 افتراضي", "😂 مضحك")
    markup.row("👨‍🍳 شيف", "💻 مبرمج")
    markup.row("🧠 طبيب نفسي", "📚 معلم")
    markup.row("🗑 مسح الذاكرة", "❓ مساعدة")
    return markup

# ========== (5) دالة OpenRouter ==========
def ask_ai(prompt):
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "google/gemini-1.5-flash",
            "messages": [{"role": "user", "content": prompt}]
        }
    )
    return response.json()["choices"][0]["message"]["content"]

# ========== (6) الأوامر ==========
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    conversations[user_id] = {"persona": PERSONAS["🤖 افتراضي"], "history": deque(maxlen=MAX_HISTORY), "last": 0}
    
    bot.send_message(
        user_id,
        "🌟 *أهلاً بك في البوت الذكي!*\n\n"
        "أنا بوت متعدد الشخصيات يعمل بـ *Gemini AI*.\n"
        "• اختر شخصية من الأسفل\n"
        "• أو اكتب سؤالك مباشرة\n"
        "• استخدم *مسح الذاكرة* لبدء محادثة جديدة\n\n"
        "_ملاحظة: الذاكرة محدودة بآخر 10 رسائل._",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(),
    )

@bot.message_handler(commands=['help'])
def help_cmd(message):
    text = (
        "📖 *كيفية الاستخدام:*\n\n"
        "1️⃣ اختر شخصية من الأزرار\n"
        "2️⃣ اكتب سؤالك\n"
        "3️⃣ البوت يتذكر السياق (آخر 10 رسائل)\n\n"
        "⚡ *الأوامر:*\n"
        "/start - بدء البوت\n"
        "/help - هذا المساعدة\n\n"
        "🧹 *مسح الذاكرة* - لمسح السياق الحالي"
    )
    bot.send_message(message.from_user.id, text, parse_mode="Markdown", reply_markup=get_main_keyboard())

# ========== (7) المعالجة ==========
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    user_text = message.text
    
    now = time.time()
    conv = conversations.get(user_id)
    if conv and (now - conv.get("last", 0)) < RATE_LIMIT_SEC:
        bot.send_message(user_id, "⏳ *بطّل شوي...*", parse_mode="Markdown")
        return
    
    if user_text in PERSONAS:
        conversations[user_id] = {"persona": PERSONAS[user_text], "history": deque(maxlen=MAX_HISTORY), "last": now}
        bot.send_message(user_id, f"✅ تم تغيير الشخصية إلى: *{user_text}*", parse_mode="Markdown", reply_markup=get_main_keyboard())
        return
    
    if user_text == "🗑 مسح الذاكرة":
        p = conv["persona"] if conv else PERSONAS["🤖 افتراضي"]
        conversations[user_id] = {"persona": p, "history": deque(maxlen=MAX_HISTORY), "last": now}
        bot.send_message(user_id, "🧹 تم مسح الذاكرة.", reply_markup=get_main_keyboard())
        return
    
    if user_text == "❓ مساعدة":
        help_cmd(message)
        return
    
    if user_id not in conversations:
        conversations[user_id] = {"persona": PERSONAS["🤖 افتراضي"], "history": deque(maxlen=MAX_HISTORY), "last": now}
    
    conv = conversations[user_id]
    conv["last"] = now
    
    # بناء المحادثة
    history_text = ""
    for turn in conv["history"]:
        history_text += f"المستخدم: {turn['user']}\nأنت: {turn['bot']}\n\n"
    
    full_prompt = (
        f"التعليمات: {conv['persona']}\n\n"
        f"محادثة سابقة:\n{history_text}\n"
        f"المستخدم الآن: {user_text}\n\n"
        f"أجب الآن:"
    )
    
    try:
        reply = ask_ai(full_prompt)
        conv["history"].append({"user": user_text, "bot": reply})
        
        if len(reply) > 4096:
            for i in range(0, len(reply), 4096):
                bot.send_message(user_id, reply[i:i+4096], reply_markup=get_main_keyboard())
        else:
            bot.send_message(user_id, reply, reply_markup=get_main_keyboard())
            
    except Exception as e:
        print(f"Error: {e}")
        bot.send_message(user_id, "⚠️ حدث خطأ تقني. جرّب مرة أخرى.", reply_markup=get_main_keyboard())

# ========== (8) التشغيل ==========
print("✅ البوت شغال...")
bot.polling(none_stop=True)
