import os
import logging
import asyncio
import time
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from redis import Redis
from rq import Queue
from dotenv import load_dotenv
from pathlib import Path

# Import services
from app.services.downloads import download_video, download_subtitle
from app.services.ai import generate_short_subtitles
from app.services.processing import process_downloaded_video
from app.services.telegram_notifier import send_video_to_telegram

# Load environment variables
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Setup Redis and Queue
try:
    redis_conn = Redis.from_url(REDIS_URL)
    queue = Queue("video_queue", connection=redis_conn)
except Exception as e:
    logger.error(f"Failed to connect to Redis: {e}")
    exit(1)

# Setup Directories
BASE_DIR = Path(__file__).parent.resolve()
DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to the Short Maker Bot!\n\n"
        "Send me a YouTube URL and I will:\n"
        "1. Download the video and subtitles\n"
        "2. Generate AI-powered highlights\n"
        "3. Create a short video\n"
        "4. Send it back to you!\n\n"
        "Just paste the link to start."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    chat_id = update.effective_chat.id
    
    # Basic URL validation
    if "youtube.com" not in url and "youtu.be" not in url:
        await update.message.reply_text("⚠️ Please send a valid YouTube URL.")
        return

    await update.message.reply_text("🚀 Processing started! I'll notify you when it's ready.\n\nSteps:\n1. Downloading Subtitles...\n2. Analyzing with AI...\n3. Downloading Video...\n4. Editing & Processing...\n5. Uploading to Telegram...")

    try:
        # Generate a unique filename base
        timestamp = int(time.time())
        # We use a simple name to ensure consistency across jobs
        # In a real multi-user app, we'd want more unique IDs or pass paths explicitly
        filename_base = f"bot_{chat_id}_{timestamp}"
        
        subtitle_filename = f"{filename_base}"
        subtitle_file_path = str(DOWNLOADS_DIR / subtitle_filename)
        
        logger.info(f"Enqueuing jobs for {url} (Chat ID: {chat_id})")

        # 1. Download Subtitle
        subtitle_job = queue.enqueue(
            download_subtitle,
            url,
            "en",
            subtitle_file_path,
            job_timeout=300
        )
        
        # 2. Generate Short Subtitles
        # Note: download_subtitle appends .en.vtt
        short_subtitle_job = queue.enqueue(
            generate_short_subtitles,
            f"{subtitle_file_path}.en.vtt",
            depends_on=subtitle_job,
            job_timeout=300
        )
        
        # 3. Download Video
        download_job = queue.enqueue(
            download_video,
            url,
            str(DOWNLOADS_DIR),
            depends_on=short_subtitle_job,
            job_timeout=1800
        )
        
        # 4. Process Video
        process_job = queue.enqueue(
            process_downloaded_video,
            depends_on=download_job,
            job_timeout=3600
        )

        # 5. Send to Telegram
        send_job = queue.enqueue(
            send_video_to_telegram,
            chat_id,
            depends_on=process_job,
            job_timeout=600
        )
        
        logger.info(f"Jobs enqueued successfully. Final job ID: {send_job.id}")

    except Exception as e:
        logger.error(f"Error enqueuing jobs: {e}")
        await update.message.reply_text(f"❌ An error occurred while starting the process: {e}")

if __name__ == '__main__':
    if not TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not found in environment variables.")
        print("Please add TELEGRAM_BOT_TOKEN to your .env file.")
        exit(1)
        
    print("Starting Bot...")
    application = ApplicationBuilder().token(TOKEN).build()
    
    start_handler = CommandHandler('start', start)
    message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    
    application.add_handler(start_handler)
    application.add_handler(message_handler)
    
    print("Bot is polling...")
    application.run_polling()
