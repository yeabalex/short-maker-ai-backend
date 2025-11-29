import os
import asyncio
from telegram import Bot
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def send_video_async(chat_id: int, video_path: str):
    if not TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not found.")
        return

    bot = Bot(token=TOKEN)
    print(f"Sending video {video_path} to {chat_id}...")
    try:
        with open(video_path, 'rb') as video:
            await bot.send_video(chat_id=chat_id, video=video, caption="Here is your processed video!", read_timeout=600, write_timeout=600, connect_timeout=600)
        print("Video sent successfully.")
    except Exception as e:
        print(f"Failed to send video: {e}")

def send_video_to_telegram(chat_id: int, video_path: str = None):
    """
    Sends the processed video to the specified Telegram chat.
    If video_path is None, it tries to find the most recent processed video.
    """
    print(f"Attempting to send video to chat_id: {chat_id}")
    
    if not video_path:
        # Try to find the most recently processed video
        # This logic mirrors process_downloaded_video but looks for *_processed.mp4
        # We assume the worker is running in the root directory or we need to find 'downloads'
        # In main.py, DOWNLOADS_DIR = BASE_DIR / "downloads"
        # Here we'll try to find 'downloads' relative to CWD or this file.
        
        # Try CWD first
        downloads_dir = Path("downloads").resolve()
        if not downloads_dir.exists():
             # Try relative to this file: app/services/../../downloads
             downloads_dir = Path(__file__).parent.parent.parent / "downloads"
             downloads_dir = downloads_dir.resolve()
        
        print(f"Looking for videos in: {downloads_dir}")
        
        if not downloads_dir.exists():
            print(f"Downloads directory not found: {downloads_dir}")
            return

        try:
            # Find files ending with _processed.mp4
            video_files = sorted(
                [f for f in downloads_dir.glob("*_processed.mp4") if f.is_file()],
                key=os.path.getmtime,
                reverse=True
            )
            if video_files:
                video_path = str(video_files[0])
                print(f"Found most recent processed video: {video_path}")
            else:
                print("No processed video found to send.")
                return
        except Exception as e:
            print(f"Error finding video files: {e}")
            return

    if not os.path.exists(video_path):
        print(f"Video file not found: {video_path}")
        return

    # Run the async function
    try:
        asyncio.run(send_video_async(chat_id, video_path))
    except Exception as e:
        print(f"Error running async send: {e}")
