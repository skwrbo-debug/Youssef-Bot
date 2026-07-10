import os
import threading
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

# ====== Token & Port ======
TOKEN = "8745236717:AAGjIacCY4SC2CtIFqDQAv5oZUEInFBg-Nk"
PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_URL = "https://youssef-bot-zdkw.onrender.com/webhook"

# ====== Auto Reply ======
AUTO_REPLY_MESSAGE = "أهلاً! 👋\nشكراً لتواصلك. سأرد عليك بأقرب وقت."
auto_reply_enabled = {}

# ====== Telegram App ======
application = Application.builder().token(TOKEN).build()

# ====== COMMANDS ======

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome = (
        f"أهلاً {user.first_name}! 👋\n\n"
        "أنا YoussefBot، بوت متعدد المهام:\n"
        "• استخراج محتوى من المواقع 🔗\n"
        "• البحث عن الموسيقى 🎵\n"
        "• الرد الآلي 🤖\n\n"
        "اكتب /help لعرض كل الأوامر."
    )
    keyboard = [
        [InlineKeyboardButton("📋 قائمة الأوامر", callback_data="help")],
        [InlineKeyboardButton("🔗 استخراج من رابط", callback_data="extract")],
        [InlineKeyboardButton("🎵 بحث موسيقى", callback_data="music")],
        [InlineKeyboardButton("🤖 تفعيل الرد الآلي", callback_data="auto_on")],
    ]
    await update.message.reply_text(welcome, reply_markup=InlineKeyboardMarkup(keyboard))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📋 <b>قائمة الأوامر:</b>\n\n"
        "<b>/start</b> - بدء البوت\n"
        "<b>/help</b> - عرض القائمة\n"
        "<b>/extract</b> &lt;رابط&gt; - استخراج محتوى من موقع\n"
        "<b>/music</b> &lt;اسم&gt; - بحث موسيقى\n"
        "<b>/auto_on</b> - تشغيل الرد الآلي\n"
        "<b>/auto_off</b> - إيقاف الرد الآلي\n"
        "<b>/status</b> - حالة البوت\n"
        "<b>/about</b> - معلومات\n"
        "<b>/settings</b> - إعدادات\n\n"
        "💡 <b>مثال:</b>\n"
        "<code>/extract https://www.wikipedia.org</code>\n"
        "<code>/music فيروز الو</code>"
    )
    await update.message.reply_text(help_text, parse_mode="HTML")

async def extract_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ <b>الاستخدام:</b>\n<code>/extract https://www.example.com</code>",
            parse_mode="HTML"
        )
        return
    url = context.args[0]
    if not url.startswith(("http://", "https://")):
        await update.message.reply_text("❌ الرابط يجب أن يبدأ بـ http:// أو https://")
        return
    
    msg = await update.message.reply_text("⏳ جاري استخراج المحتوى...")
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.content, "html.parser")
        
        images = []
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if src:
                if src.startswith("//"): src = "https:" + src
                elif src.startswith("/"): src = urljoin(url, src)
                images.append(src)
        
        videos = []
        for v in soup.find_all(["video", "iframe"]):
            src = v.get("src") or v.get("data-src")
            if src: videos.append(src)
        
        links = []
        for a in soup.find_all("a", href=True):
            h = a["href"]
            if h.startswith(("http://", "https://")): links.append(h)
        
        result = f"🔗 <b>الرابط:</b> {url}\n\n"
        result += f"🖼 <b>الصور:</b> {len(images)}\n"
        for i, img in enumerate(images[:10], 1): result += f"{i}. {img}\n"
        if len(images) > 10: result += f"... و {len(images)-10} أخرى\n"
        result += "\n"
        
        result += f"🎥 <b>الفيديوهات:</b> {len(videos)}\n"
        for i, v in enumerate(videos[:5], 1): result += f"{i}. {v}\n"
        if len(videos) > 5: result += f"... و {len(videos)-5} أخرى\n"
        result += "\n"
        
        result += f"🌐 <b>روابط:</b> {len(links)}\n"
        for i, l in enumerate(links[:10], 1): result += f"• {l}\n"
        if len(links) > 10: result += f"... و {len(links)-10} أخرى\n"
        
        result += f"\n📊 <b>المجموع:</b> {len(images)+len(videos)+len(links)} عنصر"
        await msg.edit_text(result, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        await msg.edit_text(f"❌ خطأ:\n<code>{str(e)}</code>", parse_mode="HTML")

async def music_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ <b>الاستخدام:</b>\n<code>/music اسم الأغنية</code>",
            parse_mode="HTML"
        )
        return
    query = " ".join(context.args)
    await update.message.reply_text(
        f"🎵 <b>البحث عن:</b> <i>{query}</i>\n\n"
        "أرسل رابط مباشر ينتهي بـ .mp3 أو .m4a لأشغله لك.",
        parse_mode="HTML"
    )

async def auto_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    auto_reply_enabled[chat_id] = True
    await update.message.reply_text("✅ <b>الرد الآلي مفعل!</b>", parse_mode="HTML")

async def auto_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    auto_reply_enabled[chat_id] = False
    await update.message.reply_text("❌ <b>الرد الآلي معطل.</b>", parse_mode="HTML")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    auto_status = "✅ مفعل" if auto_reply_enabled.get(chat_id, False) else "❌ معطل"
    await update.message.reply_text(
        f"📊 <b>حالة البوت:</b>\n\n🤖 الرد الآلي: {auto_status}\n"
        f"👤 المستخدم: {update.effective_user.first_name}\n"
        f"🌐 السيرفر: Render (24/7)",
        parse_mode="HTML"
    )

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 <b>YoussefBot</b>\n\n"
        "بوت متعدد المهام\n\n"
        "🖥 السيرفر: Render\n"
        "📡 المراقبة: UptimeRobot\n"
        "⚡ الحالة: شغال 24/7",
        parse_mode="HTML"
    )

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    auto_status = "✅ مفعل" if auto_reply_enabled.get(chat_id, False) else "❌ معطل"
    keyboard = [
        [InlineKeyboardButton("🔕 إيقاف الرد الآلي" if auto_reply_enabled.get(chat_id) else "🤖 تفعيل الرد الآلي", callback_data="toggle_auto")],
        [InlineKeyboardButton("📋 قائمة الأوامر", callback_data="help")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="start")],
    ]
    await update.message.reply_text(
        f"⚙️ <b>إعدادات:</b>\n\n🤖 الرد الآلي: {auto_status}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text
    if auto_reply_enabled.get(chat_id, False):
        await update.message.reply_text(AUTO_REPLY_MESSAGE)
        return
    if text.startswith(("http://", "https://")):
        context.args = [text]
        await extract_command(update, context)
        return
    await update.message.reply_text("❓ اكتب /help لعرض الأوامر.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "help": await help_command(update, context)
    elif query.data == "extract": await query.edit_message_text("🔗 اكتب: <code>/extract https://example.com</code>", parse_mode="HTML")
    elif query.data == "music": await query.edit_message_text("🎵 اكتب: <code>/music اسم الأغنية</code>", parse_mode="HTML")
    elif query.data == "auto_on":
        auto_reply_enabled[update.effective_chat.id] = True
        await query.edit_message_text("✅ <b>الرد الآلي مفعل!</b>", parse_mode="HTML")
    elif query.data == "toggle_auto":
        cid = update.effective_chat.id
        auto_reply_enabled[cid] = not auto_reply_enabled.get(cid, False)
        st = "✅ مفعل" if auto_reply_enabled[cid] else "❌ معطل"
        await query.edit_message_text(f"🤖 <b>الرد الآلي:</b> {st}", parse_mode="HTML")
    elif query.data == "start": await start_command(update, context)

# ====== REGISTER HANDLERS ======
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(CommandHandler("extract", extract_command))
application.add_handler(CommandHandler("music", music_command))
application.add_handler(CommandHandler("auto_on", auto_on_command))
application.add_handler(CommandHandler("auto_off", auto_off_command))
application.add_handler(CommandHandler("status", status_command))
application.add_handler(CommandHandler("about", about_command))
application.add_handler(CommandHandler("settings", settings_command))
application.add_handler(CallbackQueryHandler(button_callback))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# ====== WEB SERVER ======
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok", "bot": "YoussefBot"}).encode())
    
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()
    
    def do_POST(self):
        if self.path == "/webhook":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            update = Update.de_json(json.loads(post_data), application.bot)
            application.process_update(update)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()

def run_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"🚀 Server running on port {PORT}")
    server.serve_forever()

if __name__ == "__main__":
    application.initialize()
    bot = application.bot
    bot.set_webhook(url=WEBHOOK_URL)
    print(f"✅ Webhook set: {WEBHOOK_URL}")
    run_server()
