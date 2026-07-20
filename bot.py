# -*- coding: utf-8 -*-
"""
بوت تخزين ملفات على تليجرام - نسخة آمنة
========================================
"""

import os
import sqlite3
import logging
import requests
from datetime import datetime

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
# الإعدادات العامة
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

DB_PATH = "storage_bot.db"
PAGE_SIZE = 6

# نصوص الأزرار الرئيسية
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
# قاعدة البيانات
# ---------------------------------------------------------------------------

def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db_connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            file_id TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_name TEXT,
            file_size INTEGER,
            caption TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def add_file(user_id, file_id, file_type, file_name, file_size, caption):
    conn = db_connect()
    conn.execute(
        """
        INSERT INTO files (user_id, file_id, file_type, file_name, file_size, caption, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            file_id,
            file_type,
            file_name,
            file_size or 0,
            caption,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return new_id


def get_user_files(user_id, offset=0, limit=PAGE_SIZE, search=None):
    conn = db_connect()
    if search:
        rows = conn.execute(
            """
            SELECT * FROM files
            WHERE user_id = ? AND (file_name LIKE ? OR caption LIKE ?)
            ORDER BY id DESC LIMIT ? OFFSET ?
            """,
            (user_id, f"%{search}%", f"%{search}%", limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM files WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        ).fetchall()
    conn.close()
    return rows


def count_user_files(user_id, search=None):
    conn = db_connect()
    if search:
        total = conn.execute(
            "SELECT COUNT(*) FROM files WHERE user_id = ? AND (file_name LIKE ? OR caption LIKE ?)",
            (user_id, f"%{search}%", f"%{search}%"),
        ).fetchone()[0]
    else:
        total = conn.execute(
            "SELECT COUNT(*) FROM files WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
    conn.close()
    return total


def get_file_by_id(row_id, user_id):
    conn = db_connect()
    row = conn.execute(
        "SELECT * FROM files WHERE id = ? AND user_id = ?", (row_id, user_id)
    ).fetchone()
    conn.close()
    return row


def delete_file(row_id, user_id):
    conn = db_connect()
    conn.execute("DELETE FROM files WHERE id = ? AND user_id = ?", (row_id, user_id))
    conn.commit()
    conn.close()


def get_stats(user_id):
    conn = db_connect()
    row = conn.execute(
        "SELECT COUNT(*) as cnt, COALESCE(SUM(file_size),0) as total_size FROM files WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return row["cnt"], row["total_size"]


def human_size(num_bytes):
    step = 1024.0
    for unit in ["بايت", "كيلوبايت", "ميغابايت", "غيغابايت", "تيرابايت"]:
        if num_bytes < step:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= step
    return f"{num_bytes:.1f} بيتابايت"


TYPE_LABELS = {
    "document": "📄 مستند",
    "photo": "🖼️ صورة",
    "video": "🎬 فيديو",
    "audio": "🎵 صوت",
    "voice": "🎙️ رسالة صوتية",
    "animation": "🎞️ صورة متحركة",
}

# ---------------------------------------------------------------------------
# دوال مساعدة لبناء لوحات الملفات
# ---------------------------------------------------------------------------

def build_files_page(user_id, offset=0, search=None):
    rows = get_user_files(user_id, offset=offset, search=search)
    total = count_user_files(user_id, search=search)

    if total == 0:
        text = "🚫 ما في ولا ملف محفوظ حاليًا." if not search else "🚫 ما لقيت أي ملف يطابق البحث."
        return text, None

    header = f"📂 ملفاتك ({total} ملف)" if not search else f"🔍 نتائج البحث عن: {search} ({total})"
    lines = [header, ""]
    buttons = []
    for row in rows:
        label = TYPE_LABELS.get(row["file_type"], "📎 ملف")
        name = row["file_name"] or "بدون اسم"
        size = human_size(row["file_size"] or 0)
        lines.append(f"{label} | {name} | {size}")
        buttons.append(
            [InlineKeyboardButton(f"📥 {name[:25]}", callback_data=f"get:{row['id']}")]
        )

    nav_row = []
    if offset > 0:
        nav_row.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"page:{max(offset-PAGE_SIZE,0)}:{search or ''}"))
    if offset + PAGE_SIZE < total:
        nav_row.append(InlineKeyboardButton("التالي ➡️", callback_data=f"page:{offset+PAGE_SIZE}:{search or ''}"))
    if nav_row:
        buttons.append(nav_row)

    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def build_file_actions(row_id):
    buttons = [
        [InlineKeyboardButton("🗑️ حذف هذا الملف", callback_data=f"del:{row_id}")]
    ]
    return InlineKeyboardMarkup(buttons)

# ---------------------------------------------------------------------------
# الذكاء الاصطناعي (Groq)
# ---------------------------------------------------------------------------

def call_groq(user_message: str) -> str:
    """استدعاء Groq API"""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
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
        resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
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
    reply = call_groq(update.message.text)
    await update.message.reply_text(reply, reply_markup=CHAT_KEYBOARD)

# ---------------------------------------------------------------------------
# أوامر البوت
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "صديقي"
    text = (
        f"👋 أهلًا فيك يا {name}!\n\n"
        "أنا بوت التخزين الخاص فيك 📦\n"
        "ابعتلي أي ملف (صورة، فيديو، صوت، مستند...) وراح احفظه إلك فورًا،\n"
        "وتقدر ترجعله بأي وقت من زر «📂 ملفاتي».\n\n"
        "✨ ما في حد أقصى لعدد الملفات يلي احفظها إلك!\n\n"
        "اختار من الأزرار تحت 👇"
    )
    await update.message.reply_text(text, reply_markup=MAIN_KEYBOARD)


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


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    count, total_size = get_stats(user_id)
    text = (
        "📊 *إحصائيات التخزين*\n\n"
        f"📁 عدد الملفات: {count}\n"
        f"💾 الحجم الكلي: {human_size(total_size)}\n\n"
        "✅ التخزين غير محدود — استمر بإرسال ملفاتك بكل راحة."
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)


async def my_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text, markup = build_files_page(user_id, offset=0)
    await update.message.reply_text(text, reply_markup=markup or MAIN_KEYBOARD)


async def ask_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_search"] = True
    await update.message.reply_text("🔍 اكتبلي الكلمة أو اسم الملف يلي بدك تدور عليه:")

# ---------------------------------------------------------------------------
# استقبال الملفات وحفظها
# ---------------------------------------------------------------------------

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
        file_name = message.video.file_name or f"video_{message.message_id}.mp4"
        file_size = message.video.file_size
    elif message.audio:
        file_type = "audio"
        file_id = message.audio.file_id
        file_name = message.audio.file_name or (message.audio.title or f"audio_{message.message_id}.mp3")
        file_size = message.audio.file_size
    elif message.voice:
        file_type = "voice"
        file_id = message.voice.file_id
        file_name = f"voice_{message.message_id}.ogg"
        file_size = message.voice.file_size
    elif message.animation:
        file_type = "animation"
        file_id = message.animation.file_id
        file_name = message.animation.file_name or f"gif_{message.message_id}.mp4"
        file_size = message.animation.file_size
    elif message.photo:
        file_type = "photo"
        largest = message.photo[-1]
        file_id = largest.file_id
        file_name = f"photo_{message.message_id}.jpg"
        file_size = largest.file_size

    if not file_id:
        await message.reply_text("⚠️ ما قدرت أتعرف على نوع الملف، جرب ترسله من نوع تاني.")
        return

    row_id = add_file(user_id, file_id, file_type, file_name, file_size, caption)

    label = TYPE_LABELS.get(file_type, "📎 ملف")
    text = (
        "✅ تم الحفظ بنجاح!\n\n"
        f"{label}\n"
        f"📌 الاسم: {file_name}\n"
        f"💾 الحجم: {human_size(file_size or 0)}\n"
        + (f"📝 الوصف: {caption}\n" if caption else "")
        + f"\n🔢 رقم الملف: #{row_id}"
    )
    await message.reply_text(text, reply_markup=MAIN_KEYBOARD)

# ---------------------------------------------------------------------------
# استقبال الرسائل النصية
# ---------------------------------------------------------------------------

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
# الأزرار التفاعلية
# ---------------------------------------------------------------------------

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data.startswith("page:"):
        _, offset, search = data.split(":", 2)
        offset = int(offset)
        search = search or None
        text, markup = build_files_page(user_id, offset=offset, search=search)
        await query.edit_message_text(text, reply_markup=markup)

    elif data.startswith("get:"):
        row_id = int(data.split(":", 1)[1])
        row = get_file_by_id(row_id, user_id)
        if not row:
            await query.message.reply_text("⚠️ ما لقيت هاد الملف، ممكن يكون انحذف.")
            return

        caption = f"📌 {row['file_name']}\n💾 {human_size(row['file_size'] or 0)}"
        if row["caption"]:
            caption += f"\n📝 {row['caption']}"

        ftype = row["file_type"]
        fid = row["file_id"]
        chat_id = query.message.chat_id
        markup = build_file_actions(row_id)

        if ftype == "document":
            await context.bot.send_document(chat_id, fid, caption=caption, reply_markup=markup)
        elif ftype == "photo":
            await context.bot.send_photo(chat_id, fid, caption=caption, reply_markup=markup)
        elif ftype == "video":
            await context.bot.send_video(chat_id, fid, caption=caption, reply_markup=markup)
        elif ftype == "audio":
            await context.bot.send_audio(chat_id, fid, caption=caption, reply_markup=markup)
        elif ftype == "voice":
            await context.bot.send_voice(chat_id, fid, caption=caption, reply_markup=markup)
        elif ftype == "animation":
            await context.bot.send_animation(chat_id, fid, caption=caption, reply_markup=markup)

    elif data.startswith("del:"):
        row_id = int(data.split(":", 1)[1])
        delete_file(row_id, user_id)
        await query.message.reply_text("🗑️ تم حذف الملف من قائمتك بنجاح.")

# ---------------------------------------------------------------------------
# التشغيل
# ---------------------------------------------------------------------------

def main():
    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("files", my_files))

    app.add_handler(
        MessageHandler(
            filters.Document.ALL
            | filters.PHOTO
            | filters.VIDEO
            | filters.AUDIO
            | filters.VOICE
            | filters.ANIMATION,
            handle_incoming_file,
        )
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("🚀 البوت شغّال الآن...")
    app.run_polling()


if __name__ == "__main__":
    main()
                          
