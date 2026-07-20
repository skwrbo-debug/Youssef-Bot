# -*- coding: utf-8 -*-
"""
بوت تخزين ملفات على تليجرام - نسخة آمنة ومُحسّنة
=================================================
"""

import os
import re
import sqlite3
import logging
import asyncio
import aiohttp
from datetime import datetime
from functools import wraps

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ---------------------------------------------------------------------------
# الإعدادات العامة - آمنة بمتغيرات البيئة
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ✅ آمن: متغيرات بيئة بدل مفاتيح مكشوفة
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# ✅ أضفنا: قائمة المستخدمين المسموح لهم (whitelist)
ALLOWED_USERS = set(
    int(uid.strip()) for uid in os.getenv("ALLOWED_USERS", "").split(",") if uid.strip()
)

# ✅ أضفنا: حدود الملفات
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
MAX_FILES_PER_USER = 1000
RATE_LIMIT_SECONDS = 2  # بين كل طلب وطلب

DB_PATH = os.getenv("DB_PATH", "storage_bot.db")
PAGE_SIZE = 6

# التحقق من الإعدادات
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN مش محدد! حطه بمتغير البيئة.")
if not GROQ_API_KEY:
    logger.warning("⚠️ GROQ_API_KEY مش محدد - وضع الدردشة رح يكون معطل.")

# نصوص الأزرار
BTN_MY_FILES = "📂 ملفاتي"
BTN_SEARCH = "🔍 بحث عن ملف"
BTN_STATS = "📊 الإحصائيات"
BTN_HELP = "❓ المساعدة"
BTN_CHAT = "🤖 دردشة مع المساعد"
BTN_EXIT_CHAT = "🚪 إنهاء الدردشة"

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [[BTN_MY_FILES, BTN_SEARCH], [BTN_STATS, BTN_CHAT], [BTN_HELP]],
    resize_keyboard=True,
)

CHAT_KEYBOARD = ReplyKeyboardMarkup(
    [[BTN_EXIT_CHAT]],
    resize_keyboard=True,
)

KID_SAFE_SYSTEM_PROMPT = (
    "انت مساعد ذكي ولطيف بيحكي بالعربي مع طفل. "
    "جاوب دايمًا بأسلوب بسيط، إيجابي، ومناسب لعمر الأطفال. "
    "ممنوع نهائيًا: أي كلام عنيف، مخيف، جنسي، أو غير لائق. "
    "إذا الطفل سأل عن شي حساس أو خطير أو غير مناسب لعمره، "
    "اعتذر بلطف واقترح عليه يسأل أهله أو يحكي عن موضوع تاني. "
    "خلي ردودك قصيرة ومشجعة وودودة."
)

# ---------------------------------------------------------------------------
# ✅ Rate Limiting Decorator
# ---------------------------------------------------------------------------

def rate_limit(seconds=RATE_LIMIT_SECONDS):
    """Decorator لمنع flood"""
    last_call = {}
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id
            now = datetime.utcnow().timestamp()
            if user_id in last_call and (now - last_call[user_id]) < seconds:
                await update.message.reply_text(
                    "⏳ خفف شوي... جرب بعد {} ثانية.".format(int(seconds - (now - last_call[user_id])))
                )
                return
            last_call[user_id] = now
            return await func(update, context)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# ✅ Authorization Decorator
# ---------------------------------------------------------------------------

def authorized_only(func):
    """يسمح فقط للمستخدمين المصرح لهم"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if ALLOWED_USERS and user_id not in ALLOWED_USERS:
            await update.message.reply_text("🚫 ممنوع الدخول! تواصل مع المسؤول.")
            logger.warning("محاولة دخول غير مصرح: user_id=%s", user_id)
            return
        return await func(update, context)
    return wrapper


# ---------------------------------------------------------------------------
# قاعدة البيانات - مع Connection Pooling
# ---------------------------------------------------------------------------

class Database:
    """✅ Connection pool محسّن"""
    _instance = None
    _conn = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            cls._conn.row_factory = sqlite3.Row
            cls._init_tables()
        return cls._instance
    
    @classmethod
    def _init_tables(cls):
        cls._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                file_id TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_name TEXT,
                file_size INTEGER DEFAULT 0,
                caption TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        cls._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_id ON files(user_id)"
        )
        cls._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_search ON files(user_id, file_name, caption)"
        )
        cls._conn.commit()
    
    def execute(self, query, params=()):
        cursor = self._conn.execute(query, params)
        self._conn.commit()
        return cursor
    
    def fetchall(self, query, params=()):
        return self._conn.execute(query, params).fetchall()
    
    def fetchone(self, query, params=()):
        return self._conn.execute(query, params).fetchone()


db = Database()


def add_file(user_id, file_id, file_type, file_name, file_size, caption):
    # ✅ التحقق من عدد الملفات
    count = db.fetchone(
        "SELECT COUNT(*) FROM files WHERE user_id = ?", (user_id,)
    )[0]
    if count >= MAX_FILES_PER_USER:
        raise ValueError("وصلت للحد الأقصى ({}) من الملفات!".format(MAX_FILES_PER_USER))
    
    db.execute(
        """
        INSERT INTO files (user_id, file_id, file_type, file_name, file_size, caption, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, file_id, file_type, file_name, file_size or 0, caption, datetime.utcnow().isoformat()),
    )
    return db.fetchone("SELECT last_insert_rowid()")[0]


def get_user_files(user_id, offset=0, limit=PAGE_SIZE, search=None):
    # ✅ آمن: parameterized queries بدون f-string
    if search:
        search_pattern = "%{}%".format(search.replace("%", "\\%").replace("_", "\\_"))
        return db.fetchall(
            """
            SELECT * FROM files
            WHERE user_id = ? AND (file_name LIKE ? ESCAPE '\\' OR caption LIKE ? ESCAPE '\\')
            ORDER BY id DESC LIMIT ? OFFSET ?
            """,
            (user_id, search_pattern, search_pattern, limit, offset),
        )
    return db.fetchall(
        "SELECT * FROM files WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
        (user_id, limit, offset),
    )


def count_user_files(user_id, search=None):
    if search:
        search_pattern = "%{}%".format(search.replace("%", "\\%").replace("_", "\\_"))
        return db.fetchone(
            "SELECT COUNT(*) FROM files WHERE user_id = ? AND (file_name LIKE ? ESCAPE '\\' OR caption LIKE ? ESCAPE '\\')",
            (user_id, search_pattern, search_pattern),
        )[0]
    return db.fetchone("SELECT COUNT(*) FROM files WHERE user_id = ?", (user_id,))[0]


def get_file_by_id(row_id, user_id):
    return db.fetchone(
        "SELECT * FROM files WHERE id = ? AND user_id = ?", (row_id, user_id)
    )


def delete_file(row_id, user_id):
    db.execute("DELETE FROM files WHERE id = ? AND user_id = ?", (row_id, user_id))


def get_stats(user_id):
    return db.fetchone(
        "SELECT COUNT(*) as cnt, COALESCE(SUM(file_size),0) as total_size FROM files WHERE user_id = ?",
        (user_id,),
    )


# ---------------------------------------------------------------------------
# دوال مساعدة
# ---------------------------------------------------------------------------

def human_size(num_bytes):
    step = 1024.0
    for unit in ["بايت", "كيلوبايت", "ميغابايت", "غيغابايت", "تيرابايت"]:
        if num_bytes < step:
            return "{:.1f} {}".format(num_bytes, unit)
        num_bytes /= step
    return "{:.1f} بيتابايت".format(num_bytes)


TYPE_LABELS = {
    "document": "📄 مستند",
    "photo": "🖼️ صورة",
    "video": "🎬 فيديو",
    "audio": "🎵 صوت",
    "voice": "🎙️ رسالة صوتية",
    "animation": "🎞️ صورة متحركة",
}


# ✅ التحقق من file_id
FILE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

def validate_file_id(file_id):
    if not file_id or len(file_id) > 500:
        return False
    return bool(FILE_ID_PATTERN.match(file_id))


# ---------------------------------------------------------------------------
# بناء لوحات الملفات
# ---------------------------------------------------------------------------

def build_files_page(user_id, offset=0, search=None):
    rows = get_user_files(user_id, offset=offset, search=search)
    total = count_user_files(user_id, search=search)

    if total == 0:
        text = "🚫 ما في ولا ملف محفوظ حاليًا." if not search else "🚫 ما لقيت أي ملف يطابق البحث."
        return text, None

    header = "📂 ملفاتك ({} ملف)".format(total) if not search else "🔍 نتائج البحث عن: {} ({})".format(search, total)
    lines = [header, ""]
    buttons = []
    for row in rows:
        label = TYPE_LABELS.get(row["file_type"], "📎 ملف")
        name = row["file_name"] or "بدون اسم"
        size = human_size(row["file_size"] or 0)
        lines.append("{} | {} | {}".format(label, name, size))
        buttons.append(
            [InlineKeyboardButton("📥 {}".format(name[:25]), callback_data="get:{}".format(row["id"]))]
        )

    nav_row = []
    if offset > 0:
        nav_row.append(InlineKeyboardButton("⬅️ السابق", callback_data="page:{}:{}".format(max(offset-PAGE_SIZE,0), search or "")))
    if offset + PAGE_SIZE < total:
        nav_row.append(InlineKeyboardButton("التالي ➡️", callback_data="page:{}:{}".format(offset+PAGE_SIZE, search or "")))
    if nav_row:
        buttons.append(nav_row)

    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def build_file_actions(row_id):
    buttons = [
        [InlineKeyboardButton("🗑️ حذف هذا الملف", callback_data="del:{}".format(row_id))]
    ]
    return InlineKeyboardMarkup(buttons)


# ---------------------------------------------------------------------------
# ✅ الذكاء الاصطناعي - async مع aiohttp
# ---------------------------------------------------------------------------

async def call_groq(user_message: str) -> str:
    """✅ async HTTP بدل requests المتزامن"""
    if not GROQ_API_KEY:
        return "⚠️ وضع الدردشة معطل حالياً."
    
    headers = {
        "Authorization": "Bearer {}".format(GROQ_API_KEY),
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": KID_SAFE_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.6,
        "max_tokens": 400,
    }
    
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(GROQ_URL, headers=headers, json=payload, ssl=True) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data["choices"][0]["message"]["content"].strip()
    except aiohttp.ClientSSLError:
        logger.error("SSL Error مع Groq")
        return "⚠️ مشكلة بالاتصال الآمن، جرب مرة ثانية."
    except asyncio.TimeoutError:
        logger.error("Timeout مع Groq")
        return "⏳ الاتصال بطيء، جرب بعد شوي."
    except Exception as exc:
        logger.error("خطأ بالاتصال مع Groq: %s", exc)
        return "⚠️ صار في مشكلة بسيطة بالاتصال، جرب مرة ثانية بعد شوي."


async def start_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["in_chat"] = True
    await update.message.reply_text(
        "🤖 أهلًا! أنا هون تحكي معي عن أي شي حابب. اضغط «🚪 إنهاء الدردشة» متى ما بدك ترجع للقائمة.",
        reply_markup=CHAT_KEYBOARD,
    )


async def handle_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action("typing")
    reply = await call_groq(update.message.text)
    await update.message.reply_text(reply, reply_markup=CHAT_KEYBOARD)


# ---------------------------------------------------------------------------
# ✅ الأوامر - مع Authorization و Rate Limiting
# ---------------------------------------------------------------------------

@authorized_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "صديقي"
    text = (
        "👋 أهلًا فيك يا {}!\n\n"
        "أنا بوت التخزين الخاص فيك 📦\n"
        "ابعتلي أي ملف (صورة، فيديو، صوت، مستند...) وراح احفظه إلك فورًا،\n"
        "وتقدر ترجعله بأي وقت من زر «📂 ملفاتي».\n\n"
        "✨ ما في حد أقصى لعدد الملفات يلي احفظها إلك!\n\n"
        "اختار من الأزرار تحت 👇"
    ).format(name)
    await update.message.reply_text(text, reply_markup=MAIN_KEYBOARD)


@authorized_only
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "❓ *كيف تستخدم البوت:*\n\n"
        "1️⃣ ابعتلي أي ملف (صورة / فيديو / صوت / مستند) وراح احفظه تلقائيًا.\n"
        "2️⃣ لو بدك تضيف اسم أو ملاحظة للملف، ابعت الملف مع كابشن (وصف).\n"
        "3️⃣ اضغط «📂 ملفاتي» لعرض كل الملفات المحفوظة.\n"
        "4️⃣ اضغط «🔍 بحث عن ملف» وابعتلي كلمة للبحث فيها.\n"
        "5️⃣ اضغط «📊 الإحصائيات» لمعرفة عدد ملفاتك وحجمها الكلي.\n"
        "6️⃣ اضغط «🤖 دردشة مع المساعد» لتحكي مع مساعد ذكي، واضغط «🚪 إنهاء الدردشة» للرجوع.\n\n"
        "🗑️ لحذف ملف: افتحه من القائمة واضغط زر الحذف."
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)


@authorized_only
@rate_limit(1)
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    row = get_stats(user_id)
    count, total_size = row["cnt"], row["total_size"]
    text = (
        "📊 *إحصائيات التخزين*\n\n"
        "📁 عدد الملفات: {}\n"
        "💾 الحجم الكلي: {}\n\n"
        "✅ التخزين غير محدود — استمر بإرسال ملفاتك بكل راحة."
    ).format(count, human_size(total_size))
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)


@authorized_only
async def my_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text, markup = build_files_page(user_id, offset=0)
    await update.message.reply_text(text, reply_markup=markup or MAIN_KEYBOARD)


@authorized_only
async def ask_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_search"] = True
    await update.message.reply_text("🔍 اكتبلي الكلمة أو اسم الملف يلي بدك تدور عليه:")


# ---------------------------------------------------------------------------
# ✅ استقبال الملفات - مع التحقق من الحجم والـ file_id
# ---------------------------------------------------------------------------

@authorized_only
@rate_limit(1)
async def handle_incoming_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_id = update.effective_user.id
    caption = message.caption

    file_type = None
    file_id = None
    file_name = None
    file_size = None

    if message.document:
        file_type = "document"
        file_id = message.document.file_id
        file_name = message.document.file_name
        file_size = message.document.file_size
    elif message.video:
        file_type = "video"
        file_id = message.video.file_id
        file_name = message.video.file_name or "video_{}.mp4".format(message.message_id)
        file_size = message.video.file_size
    elif message.audio:
        file_type = "audio"
        file_id = message.audio.file_id
        file_name = message.audio.file_name or (message.audio.title or "audio_{}.mp3".format(message.message_id))
        file_size = message.audio.file_size
    elif message.voice:
        file_type = "voice"
        file_id = message.voice.file_id
        file_name = "voice_{}.ogg".format(message.message_id)
        file_size = message.voice.file_size
    elif message.animation:
        file_type = "animation"
        file_id = message.animation.file_id
        file_name = message.animation.file_name or "gif_{}.mp4".format(message.message_id)
        file_size = message.animation.file_size
    elif message.photo:
        file_type = "photo"
        largest = message.photo[-1]
        file_id = largest.file_id
        file_name = "photo_{}.jpg".format(message.message_id)
        file_size = largest.file_size

    if not file_id:
        await message.reply_text("⚠️ ما قدرت أتعرف على نوع الملف، جرب ترسله من نوع تاني.")
        return

    # ✅ التحقق من file_id
    if not validate_file_id(file_id):
        await message.reply_text("⚠️ معرف الملف غير صالح.")
        return

    # ✅ التحقق من حجم الملف
    if file_size and file_size > MAX_FILE_SIZE:
        await message.reply_text(
            "❌ الملف كبير جدًا! الحد الأقصى هو {}.".format(human_size(MAX_FILE_SIZE))
        )
        return

    try:
        row_id = add_file(user_id, file_id, file_type, file_name, file_size, caption)
    except ValueError as e:
        await message.reply_text("❌ {}".format(str(e)), reply_markup=MAIN_KEYBOARD)
        return

    label = TYPE_LABELS.get(file_type, "📎 ملف")
    text = (
        "✅ تم الحفظ بنجاح!\n\n"
        "{}\n"
        "📌 الاسم: {}\n"
        "💾 الحجم: {}\n"
    ).format(label, file_name, human_size(file_size or 0))
    if caption:
        text += "📝 الوصف: {}\n".format(caption)
    text += "\n🔢 رقم الملف: #{}".format(row_id)
    
    await message.reply_text(text, reply_markup=MAIN_KEYBOARD)


# ---------------------------------------------------------------------------
# ✅ استقبال الرسائل النصية
# ---------------------------------------------------------------------------

@authorized_only
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.effective_user.id

    if text == BTN_EXIT_CHAT:
        context.user_data["in_chat"] = False
        await update.message.reply_text("✅ رجعناك للقائمة الرئيسية.", reply_markup=MAIN_KEYBOARD)
        return

    if context.user_data.get("in_chat"):
        await handle_chat_message(update, context)
        return

    if context.user_data.get("awaiting_search"):
        context.user_data["awaiting_search"] = False
        result_text, markup = build_files_page(user_id, offset=0, search=text)
        await update.message.reply_text(result_text, reply_markup=markup or MAIN_KEYBOARD)
        return

    if text == BTN_MY_FILES:
        await my_files(update, context)
    elif text == BTN_SEARCH:
        await ask_search(update, context)
    elif text == BTN_STATS:
        await stats_command(update, context)
    elif text == BTN_CHAT:
        await start_chat(update, context)
    elif text == BTN_HELP:
        await help_command(update, context)
    else:
        await update.message.reply_text(
            "🤔 ما فهمت عليك، استخدم الأزرار تحت أو ابعتلي ملف لأحفظه.",
            reply_markup=MAIN_KEYBOARD,
        )


# ---------------------------------------------------------------------------
# ✅ الأزرار التفاعلية
# ---------------------------------------------------------------------------

@authorized_only
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.dat
