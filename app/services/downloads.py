import os
from pathlib import Path
from typing import Optional
from yt_dlp import YoutubeDL
import time
from urllib.parse import urlparse, parse_qs

def download_video(url: str, output_folder: str = "downloads") -> Optional[str]:
    """Download a video and return its path."""
    
    # Create output directory if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)
    
    # Generate a unique filename based on video ID and timestamp
    video_id = None
    try:
        # Try to extract video ID from URL
        parsed = urlparse(url)
        if parsed.hostname and 'youtube.com' in parsed.hostname:
            video_id = parse_qs(parsed.query).get('v', [None])[0]
        elif parsed.hostname and 'youtu.be' in parsed.hostname:
            video_id = parsed.path[1:]
    except Exception as e:
        print(f"Warning: Could not extract video ID: {e}")
    
    # Create a unique filename
    timestamp = int(time.time())
    if video_id:
        output_filename = f"{video_id}_{timestamp}.mp4"
    else:
        output_filename = f"video_{timestamp}.mp4"
    
    output_path = Path(output_folder) / output_filename
    
    ydl_opts = {
        "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(output_path),
        "writesubtitles": False,
        "writeautomaticsub": False,
        "subtitleslangs": ['en'],
        "subtitlesformat": 'srt',
        "n_threads": 8,
        "concurrent_fragment_downloads": 8,
        "quiet": True,
        "retries": 10,
        "ignoreerrors": True,
        "nooverwrites": True,
        "continuedl": True
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            if not info_dict:
                return None
                
            # Get the actual downloaded filename
            video_path = ydl.prepare_filename(info_dict)
            if not os.path.exists(video_path):
                video_path = str(output_path)
                
            return video_path
    except Exception as e:
        print(f"Error downloading video: {e}")
        return None

def download_subtitle(url: str, lang: str = "en", output_name: str = "subtitle.en.vtt") -> Optional[str]:
    """
    Download subtitles from a YouTube video as WebVTT (preferred).
    Returns path to the subtitle file if successful, else None.
    """
    try:
        # Fetch info first to know what exists
        with YoutubeDL({'skip_download': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            subs = info.get("subtitles", {})
            auto = info.get("automatic_captions", {})

        if lang in subs:
            write_automatic = False
        elif lang in auto:
            write_automatic = True
        else:
            # No subtitles in requested language
            return None

        # Request VTT instead of SRT to preserve timing fidelity
        ydl_opts = {
            'writesubtitles': True,
            'subtitleslangs': [lang],
            'writeautomaticsub': write_automatic,
            'skip_download': True,
            'subtitlesformat': 'vtt',   # <-- keep as vtt
            'outtmpl': output_name
        }

        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        return output_name if os.path.exists(output_name) else None

    except Exception as e:
        print(f"Error downloading subtitles: {e}")
        return None
