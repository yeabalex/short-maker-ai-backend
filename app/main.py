import os
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from redis import Redis
from rq import Queue
from rq.job import Job
from dotenv import load_dotenv
from pathlib import Path
from app.services.downloads import download_video, download_subtitle
from app.services.ai import generate_short_subtitles
from app.services.processing import process_downloaded_video
from app.schemas import SubtitleRequest, DownloadRequest, ShortSubtitleRequest

load_dotenv()

# Redis connection and queue
redis_url = os.getenv("REDIS_URL")
redis_conn = Redis.from_url(redis_url)
queue = Queue("video_queue", connection=redis_conn)

# FastAPI app
app = FastAPI()

# Define a consistent base directory for all files
# app/main.py -> parent is app -> parent is root
BASE_DIR = Path(__file__).parent.parent.resolve()
DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

# -----------------------
# Endpoints
# -----------------------
@app.post("/start-download")
def start_download(request: DownloadRequest):
    try:
        # Use absolute paths from the start, in the downloads directory
        subtitle_filename = f"{request.title}"
        subtitle_file_path = str(DOWNLOADS_DIR / subtitle_filename)
        
        # First, download the subtitles with absolute path
        subtitle_job = queue.enqueue(
            download_subtitle,
            request.url,
            "en",
            subtitle_file_path  # Use absolute path
        )
        print(f"Enqueued subtitle download job: {subtitle_job.id}")
        print(f"Subtitle will be saved to: {subtitle_file_path}")
        
        
        # Then generate short subtitles - use the same absolute path
        short_subtitle_job = queue.enqueue(
            generate_short_subtitles,
            f"{subtitle_file_path}.en.vtt",  # Already absolute
            depends_on=subtitle_job,
            job_timeout=300
        )
        print(f"Enqueued short subtitle generation job: {short_subtitle_job.id}")
        
        # Then download the video
        download_job = queue.enqueue(
            download_video,
            request.url,
            str(DOWNLOADS_DIR),  # Use absolute path for downloads folder
            depends_on=short_subtitle_job,
            job_timeout=1800
        )
        print(f"Enqueued video download job: {download_job.id}")
        
        # Finally, process the video with the generated short subtitles
        process_job = queue.enqueue(
            process_downloaded_video,
            depends_on=download_job,
            job_timeout=3600
        )
        print(f"Enqueued video processing job: {process_job.id}")
        
        return {
            "status": "success",
            "message": "All jobs enqueued successfully",
            "jobs": {
                "subtitle_job_id": subtitle_job.id,
                "short_subtitle_job_id": short_subtitle_job.id,
                "download_job_id": download_job.id,
                "process_job_id": process_job.id
            },
            "paths": {
                "subtitle_file": subtitle_file_path,
                "downloads_dir": str(DOWNLOADS_DIR)
            }
        }
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "message": f"Failed to enqueue jobs: {str(e)}",
            "traceback": traceback.format_exc()
        }

@app.get("/status/{job_id}")
def job_status(job_id: str):
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        return {"status": job.get_status(), "result": job.result}
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Job not found: {e}")

@app.get("/download")
def download(path: str):
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path, filename="final_output.mp4", media_type="video/mp4")
