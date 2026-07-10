import os
import threading
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from http.server import HTTPServer, BaseHTTPRequestHandler

# ====== Token & Port ======
TOKEN = "8745236717:AAGjIacCY4SC2CtIFqDQAv5oZUEInFBg-Nk"
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

def run_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"Server running on port {PORT}")
    server.serve_forever()

# ====== Telegram Bot ======
async def start(update: Update, context):
    await update.message.reply_text("Bot is running! Send a URL to extract content.")

async def handle_message(update: Update, context):
    text = update.message.text
    if text.startswith(("http://", "https://")):
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(text, headers=headers, timeout=15)
            soup = BeautifulSoup(resp.content, "html.parser")
            
            images = []
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-src")
                if src:
                    if src.startswith("//"): src = "https:" + src
                    elif src.startswith("/"): src = urljoin(text, src)
                    images.append(src)
            
            videos = []
            for v in soup.find_all(["video", "iframe"]):
                src = v.get("src") or v.get("data-src")
                if src: videos.append(src)
            
            links = []
            for a in soup.find_all("a", href=True):
                h = a["href"]
                if h.startswith(("http://", "https://")): links.append(h)
            
            result = f"URL: {text}\n\n"
            result += f"Images: {len(images)}\n"
            for i, img in enumerate(images[:10], 1): result += f"{i}. {img}\n"
            if len(images) > 10: result += f"... and {len(images)-10} more\n"
            result += f"\nVideos: {len(videos)}\n"
            for i, v in enumerate(videos[:5], 1): result += f"{i}. {v}\n"
            if len(videos) > 5: result += f"... and {len(videos)-5} more\n"
            result += f"\nLinks: {len(links)}\n"
            for i, l in enumerate(links[:10], 1): result += f"• {l}\n"
            if len(links) > 10: result += f"... and {len(links)-10} more\n"
            result += f"\nTotal: {len(images)+len(videos)+len(links)} items"
            
            await update.message.reply_text(result, disable_web_page_preview=True)
        except Exception as e:
            await update.message.reply_text(f"Error: {str(e)}")
    else:
        await update.message.reply_text("Send a valid URL starting with http:// or https://")

# ====== Main ======
if __name__ == "__main__":
    # Start web server in background
    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    
    # Start Telegram bot
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot is running...")
    app.run_polling()
