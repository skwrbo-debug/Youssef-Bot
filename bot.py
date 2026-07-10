import os
import threading
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from http.server import HTTPServer, BaseHTTPRequestHandler

TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
PORT = int(os.environ.get("PORT", 8080))

# ====== Web Server (لـ Render) ======
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")
    
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_web_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    server.serve_forever()

# ====== جلب الروابط ======
def extract_links(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        r = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        result = {'all': [], 'images': [], 'videos': [], 'files': [], 'pages': []}
        
        for tag in soup.find_all(['a', 'img', 'video', 'source', 'link']):
            link = tag.get('href') or tag.get('src')
            if not link:
                continue
            
            full = urljoin(url, link)
            path = urlparse(full).path.lower()
            
            if any(path.endswith(e) for e in ['.jpg','.jpeg','.png','.gif','.webp','.svg','.ico','.bmp']):
                result['images'].append(full)
            elif any(path.endswith(e) for e in ['.mp4','.webm','.mkv','.avi','.mov','.m3u8','.flv']):
                result['videos'].append(full)
            elif any(path.endswith(e) for e in ['.pdf','.zip','.rar','.doc','.docx','.xls','.xlsx','.mp3','.apk','.exe','.tar','.gz']):
                result['files'].append(full)
            elif full.startswith('http'):
                result['pages'].append(full)
            
            result['all'].append(full)
        
        for k in result:
            result[k] = list(dict.fromkeys(result[k]))
        
        return result
    except Exception as e:
        return str(e)

# ====== Telegram Handlers ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلاً يوسف!\n\n"
        "أبعثلي رابط أي موقع وبجيبلك كل الروابط فيه:\n"
        "• 🖼 صور\n"
        "• 🎥 فيديوهات\n"
        "• 📁 ملفات\n"
        "• 🌐 روابط صفحات\n\n"
        "مثال: https://example.com"
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    if not url.startswith(('http://', 'https://')):
        await update.message.reply_text("❌ أبعث رابط صحيح يبدأ بـ http:// أو https://")
        return
    
    msg = await update.message.reply_text("⏳ جاري البحث عن الروابط...")
    
    result = extract_links(url)
    
    if isinstance(result, str):
        await msg.edit_text(f"❌ صار خطأ:\n`{result}`", parse_mode='Markdown')
        return
    
    text = f"🔗 **الروابط في:** `{url}`\n\n"
    
    if result['images']:
        text += f"🖼 **الصور:** {len(result['images'])}\n"
        for i, img in enumerate(result['images'][:15], 1):
            text += f"{i}. `{img}`\n"
        if len(result['images']) > 15:
            text += f"... و {len(result['images'])-15} صورة تاني\n"
        text += "\n"
    
    if result['videos']:
        text += f"🎥 **الفيديوهات:** {len(result['videos'])}\n"
        for v in result['videos'][:10]:
            text += f"• `{v}`\n"
        if len(result['videos']) > 10:
            text += f"... و {len(result['videos'])-10} فيديو تاني\n"
        text += "\n"
    
    if result['files']:
        text += f"📁 **الملفات:** {len(result['files'])}\n"
        for f in result['files'][:10]:
            text += f"• `{f}`\n"
        if len(result['files']) > 10:
            text += f"... و {len(result['files'])-10} ملف تاني\n"
        text += "\n"
    
    if result['pages']:
        text += f"🌐 **روابط الصفحات:** {len(result['pages'])}\n"
        for p in result['pages'][:10]:
            text += f"• `{p}`\n"
        if len(result['pages']) > 10:
            text += f"... و {len(result['pages'])-10} رابط تاني\n"
    
    total = len(result['all'])
    if not any(result[k] for k in ['images','videos','files','pages']):
        text += "❌ ما لقيت ولا رابط."
    else:
        text += f"\n📊 **المجموع:** {total} رابط"
    
    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        await msg.delete()
        for part in parts:
            await update.message.reply_text(part, parse_mode='Markdown')
    else:
        await msg.edit_text(text, parse_mode='Markdown')

# ====== Main ======
def main():
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    print(f"✅ Web server شغال على port {PORT}")
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    
    print("🤖 البوت شغال...")
    app.run_polling()

if __name__ == "__main__":
    main()
