import os
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

TOKEN = "8745236717:AAGjIacCY4SC2CtIFqDQAv5oZUEInFBg-Nk"
PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_URL = "https://youssef-bot-zdkw.onrender.com/webhook"

auto_reply_enabled = {}

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== COMMANDS ==========

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome = f"Hello {user.first_name}! 👋\n\nI am YoussefBot:\n• Extract content from websites 🔗\n• Music search 🎵\n• Auto-reply 🤖\n\nType /help for commands."
    keyboard = [
        [InlineKeyboardButton("📋 Commands", callback_data="help")],
        [InlineKeyboardButton("🔗 Extract URL", callback_data="extract")],
        [InlineKeyboardButton("🎵 Music", callback_data="music")],
        [InlineKeyboardButton("🤖 Auto-reply ON", callback_data="auto_on")],
    ]
    await update.message.reply_text(welcome, reply_markup=InlineKeyboardMarkup(keyboard))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📋 <b>Commands:</b>\n\n"
        "<b>/start</b> - Start bot\n"
        "<b>/help</b> - Show commands\n"
        "<b>/extract</b> &lt;url&gt; - Extract content\n"
        "<b>/music</b> &lt;name&gt; - Search music\n"
        "<b>/auto_on</b> - Enable auto-reply\n"
        "<b>/auto_off</b> - Disable auto-reply\n"
        "<b>/status</b> - Bot status\n"
        "<b>/about</b> - About\n"
        "<b>/settings</b> - Settings"
    )
    await update.message.reply_text(help_text, parse_mode="HTML")

async def extract_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage:\n<code>/extract https://www.example.com</code>", parse_mode="HTML")
        return
    url = context.args[0]
    if not url.startswith(("http://", "https://")):
        await update.message.reply_text("❌ URL must start with http:// or https://")
        return
    msg = await update.message.reply_text("⏳ Extracting content...")
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
        result = f"🔗 <b>URL:</b> {url}\n\n"
        result += f"🖼 <b>Images:</b> {len(images)}\n"
        for i, img in enumerate(images[:10], 1): result += f"{i}. {img}\n"
        if len(images) > 10: result += f"... and {len(images)-10} more\n"
        result += f"\n🎥 <b>Videos:</b> {len(videos)}\n"
        for i, v in enumerate(videos[:5], 1): result += f"{i}. {v}\n"
        if len(videos) > 5: result += f"... and {len(videos)-5} more\n"
        result += f"\n🌐 <b>Links:</b> {len(links)}\n"
        for i, l in enumerate(links[:10], 1): result += f"• {l}\n"
        if len(links) > 10: result += f"... and {len(links)-10} more\n"
        result += f"\n📊 <b>Total:</b> {len(images)+len(videos)+len(links)} items"
        await msg.edit_text(result, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        await msg.edit_text(f"❌ Error:\n<code>{str(e)}</code>", parse_mode="HTML")

async def music_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage:\n<code>/music song name</code>", parse_mode="HTML")
        return
    query = " ".join(context.args)
    await update.message.reply_text(f"🎵 <b>Searching:</b> <i>{query}</i>\n\nSend direct .mp3 or .m4a link to play.", parse_mode="HTML")

async def auto_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    auto_reply_enabled[chat_id] = True
    await update.message.reply_text("✅ <b>Auto-reply ON!</b>", parse_mode="HTML")

async def auto_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    auto_reply_enabled[chat_id] = False
    await update.message.reply_text("❌ <b>Auto-reply OFF.</b>", parse_mode="HTML")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    auto_status = "✅ ON" if auto_reply_enabled.get(chat_id, False) else "❌ OFF"
    await update.message.reply_text(f"📊 <b>Status:</b>\n\n🤖 Auto-reply: {auto_status}\n👤 User: {update.effective_user.first_name}\n🌐 Server: Render (24/7)", parse_mode="HTML")

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 <b>YoussefBot</b>\n\nMulti-purpose bot\n\n🖥 Server: Render\n📡 Monitor: UptimeRobot\n⚡ Status: 24/7", parse_mode="HTML")

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    auto_status = "✅ ON" if auto_reply_enabled.get(chat_id, False) else "❌ OFF"
    keyboard = [
        [InlineKeyboardButton("🔕 Auto-reply OFF" if auto_reply_enabled.get(chat_id) else "🤖 Auto-reply ON", callback_data="toggle_auto")],
        [InlineKeyboardButton("📋 Commands", callback_data="help")],
        [InlineKeyboardButton("🔙 Back", callback_data="start")],
    ]
    await update.message.reply_text(f"⚙️ <b>Settings:</b>\n\n🤖 Auto-reply: {auto_status}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text
    if auto_reply_enabled.get(chat_id, False):
        await update.message.reply_text("Hello! 👋\nThanks for contacting me. I will reply soon.")
        return
    if text.startswith(("http://", "https://")):
        context.args = [text]
        await extract_command(update, context)
        return
    await update.message.reply_text("❓ Type /help for commands.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "help": await help_command(update, context)
    elif query.data == "extract": await query.edit_message_text("🔗 Type: <code>/extract https://example.com</code>", parse_mode="HTML")
    elif query.data == "music": await query.edit_message_text("🎵 Type: <code>/music song name</code>", parse_mode="HTML")
    elif query.data == "auto_on":
        auto_reply_enabled[update.effective_chat.id] = True
        await query.edit_message_text("✅ <b>Auto-reply ON!</b>", parse_mode="HTML")
    elif query.data == "toggle_auto":
        cid = update.effective_chat.id
        auto_reply_enabled[cid] = not auto_reply_enabled.get(cid, False)
        st = "✅ ON" if auto_reply_enabled[cid] else "❌ OFF"
        await query.edit_message_text(f"🤖 <b>Auto-reply:</b> {st}", parse_mode="HTML")
    elif query.data == "start": await start_command(update, context)

# ========== REGISTER ==========
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

# ========== WEB SERVER ==========
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
