from yt_dlp import YoutubeDL
from pathlib import Path
import subprocess
import os
import uuid
import re
import json
from typing import Dict, List, Any, Optional, Union
from google import genai
from google.genai import types
import time
from dotenv import load_dotenv

load_dotenv()

client = genai.Client()
VIDEO_FILENAME = "input.mp4"

def sanitize_json_string(json_str: str) -> str:
    """Sanitize a JSON string by removing markdown code blocks and invalid characters."""
    if not json_str or not isinstance(json_str, str):
        return json_str
    
    # Remove markdown code blocks (```json and ```)
    json_str = re.sub(r'^```(?:json)?\s*|```$', '', json_str, flags=re.MULTILINE)
    
    # Remove any remaining backticks that might break JSON
    json_str = json_str.replace('`', '')
    
    # Remove any non-printable characters except newlines and tabs
    json_str = ''.join(char for char in json_str if char.isprintable() or char in '\n\r\t')
    
    # Remove BOM (Byte Order Mark) if present
    if json_str.startswith('\ufeff'):
        json_str = json_str[1:]
    
    # Remove any leading/trailing whitespace
    return json_str.strip()

def parse_json_safely(json_str: str) -> Union[Dict, List, None]:
    """Safely parse a JSON string with proper error handling and sanitization."""
    if not json_str:
        return None
    
    try:
        # First sanitize the string
        sanitized = sanitize_json_string(json_str)
        # Try to parse the JSON
        return json.loads(sanitized)
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error parsing JSON: {e}")
        return None

def extract_timestamps_from_srt(srt_content: str) -> List[Dict[str, Any]]:
    """Extract timestamps and text from SRT content."""
    timestamps = []
    blocks = re.split(r'\n\s*\n', srt_content.strip())
    
    for block in blocks:
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        if len(lines) < 2:
            continue
            
        # Parse the timestamp line (e.g., "00:00:01,280 --> 00:00:07,359")
        timestamp_match = re.match(
            r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-{2}>\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})',
            lines[1]
        )
        
        if not timestamp_match:
            continue
            
        # Convert timestamp to seconds
        def parse_time(h, m, s, ms):
            return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
            
        start_sec = parse_time(*timestamp_match.group(1, 2, 3, 4))
        end_sec = parse_time(*timestamp_match.group(5, 6, 7, 8))
        
        # Get the text (all lines after the timestamp)
        text = ' '.join(lines[2:])
        
        # Add to timestamps
        timestamps.append({
            'start_sec': start_sec,
            'end_sec': end_sec,
            'text': text
        })
    
    return timestamps

def process_downloaded_video():
    """Process a downloaded video using pre-generated short subtitles."""
    from pathlib import Path
    
    # Get absolute path to downloads directory
    downloads_dir = Path("downloads").resolve()
    
    # Ensure downloads directory exists
    if not downloads_dir.exists():
        downloads_dir.mkdir(parents=True, exist_ok=True)
    
    # Find the most recently downloaded video
    video_files = []
    try:
        video_files = sorted(
            [f for f in downloads_dir.glob("*.mp4") if f.is_file()],
            key=os.path.getmtime,
            reverse=True
        )
    except Exception as e:
        print(f"Error finding video files: {e}")
        return None
    
    if not video_files:
        print(f"No video files found in {downloads_dir}")
        return None
        
    video_path = str(video_files[0].resolve())
    print(f"Processing video: {video_path}")
    
    # Get the base path without extension for finding related files
    base_path = Path(video_path).with_suffix('')
    
    # Look for the short subtitles JSON file
    short_json_files = sorted(downloads_dir.glob("*.short.json"), key=os.path.getmtime, reverse=True)
    
    if not short_json_files:
        print(f"No short subtitle files (*.short.json) found in {downloads_dir}")
        return None
        
    json_path = short_json_files[0].resolve()
    print(f"Using short subtitles from: {json_path}")
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                timestamps = data
            elif isinstance(data, dict) and 'timestamps' in data:
                timestamps = data['timestamps']
            else:
                print("JSON structure not recognized")
                return None
            
            # Keep original timestamps without any adjustments
            pass
                    
        print(f"Loaded {len(timestamps)} timestamps from short subtitles")
    except Exception as e:
        print(f"Error reading short subtitles file {json_path}: {e}")
        return None
    
    if not timestamps:
        print("No timestamps found for video processing")
        return None
    
    print(f"Found {len(timestamps)} timestamps, starting cut and merge...")
    
    # Create output filename with _processed suffix using absolute path
    video_path_obj = Path(video_path)
    output_path = video_path_obj.with_name(f"{video_path_obj.stem}_processed{video_path_obj.suffix}")
    output_path = output_path.resolve()
    
    print(f"Output will be saved to: {output_path}")
    
    # Process the video with the found timestamps
    try:
        result_path = cut_and_merge(str(video_path_obj.resolve()), timestamps, str(output_path))
        result_path = Path(result_path).resolve() if result_path else None
        
        if result_path and result_path.exists():
            print(f"Successfully processed video: {result_path}")
            return str(result_path)
        else:
            print("Failed to process video - cut_and_merge returned no output or file doesn't exist")
            if result_path:
                print(f"Expected output path was: {result_path}")
            return None
    except Exception as e:
        print(f"Error during cut and merge: {str(e)}")
        import traceback
        traceback.print_exc()
        return None
    
    return output_path


def download_video(url: str, output_folder: str = "downloads") -> Optional[str]:
    """Download a video and return its path."""
    import time
    from urllib.parse import urlparse, parse_qs
    
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
        "writesubtitles": True,
        "writeautomaticsub": True,
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

def extract_timestamps_from_source(video_path: str, info_dict: dict = None) -> List[Dict[str, Any]]:
    """Extract timestamps from various sources (SRT, description, etc.)"""
    # Try to find and parse SRT file first
    base_path = os.path.splitext(video_path)[0]
    srt_path = f"{base_path}.en.srt"
    
    if os.path.exists(srt_path):
        try:
            with open(srt_path, 'r', encoding='utf-8') as f:
                srt_content = f.read()
                timestamps = extract_timestamps_from_srt(srt_content)
                if timestamps:
                    return timestamps
        except Exception as e:
            print(f"Warning: Failed to parse SRT file: {e}")
    
    # Fall back to parsing description for timestamps if info_dict is provided
    if info_dict and 'description' in info_dict:
        description = info_dict['description']
        if description:
            # Look for JSON in the description
            json_matches = re.findall(r'```(?:json)?\s*({.*?})\s*```', description, re.DOTALL)
            for json_str in json_matches:
                try:
                    data = parse_json_safely(json_str)
                    if isinstance(data, list):
                        return data
                    elif isinstance(data, dict) and 'timestamps' in data:
                        return data['timestamps']
                except Exception as e:
                    print(f"Warning: Failed to parse JSON from description: {e}")
    
    return []

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

def cut_and_merge(input_video: str, timestamps: list, output_name: str = "final_output.mp4") -> Optional[str]:
    """
    Cut and merge video segments based on timestamps.
    Returns the path to the output video if successful, else None.
    """
    if not os.path.exists(input_video):
        print(f"Error: Input video not found: {input_video}")
        return None
        
    if not timestamps or not isinstance(timestamps, list):
        print("Error: Invalid timestamps provided")
        return None
        
    session_id = str(uuid.uuid4())
    work_dir = Path(f"session_{session_id}")
    work_dir.mkdir(exist_ok=True)
        
    clips_dir = work_dir / "clips"
    clips_dir.mkdir(exist_ok=True)
        
    clip_names = []
        
    for i, ts in enumerate(timestamps, start=1):
        clip_name = f"clip_{i}.mp4"
        clip_path = clips_dir / clip_name
        clip_names.append(clip_name)

        subprocess.run([
            "ffmpeg",
            "-y",
            "-i", input_video,
            "-ss", str(ts["start_sec"]),
            "-to", str(ts["end_sec"]),
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "slow",
            "-c:a", "aac",
            "-b:a", "192k",
            str(clip_path)
        ], check=True)
                
    list_file = clips_dir / "list.txt"
    with open(list_file, "w") as f:
        for name in clip_names:
            f.write(f"file '{name}'\n")
        
    output_path = work_dir / output_name
        
    subprocess.run([
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", "list.txt",
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "slow",
        "-c:a", "aac",
        "-b:a", "192k",
        str(output_path)
    ], cwd=str(clips_dir), check=True)

    return str(output_path)

def convert_vtt_to_srt(vtt_file: str) -> str:
    """
    Convert a VTT subtitle file to SRT format.
    Returns the path to the converted SRT file.
    """
    if not vtt_file.lower().endswith('.vtt'):
        return vtt_file  # Not a VTT file, return as is
    
    srt_file = vtt_file[:-4] + '.srt'
    
    with open(vtt_file, 'r', encoding='utf-8') as vtt, \
         open(srt_file, 'w', encoding='utf-8') as srt:
        
        lines = vtt.readlines()
        line_number = 1
        i = 0
        
        # Skip WebVTT header if present
        while i < len(lines) and lines[i].strip().upper() != '':
            if lines[i].strip().upper() == 'WEBVTT':
                i += 1
                break
            i += 1
        
        # Process the rest of the file
        while i < len(lines):
            # Skip empty lines
            if not lines[i].strip():
                i += 1
                continue
                
            # Write subtitle number
            srt.write(f"{line_number}\n")
            line_number += 1
            
            # Write timestamp (VTT and SRT use the same format)
            srt.write(lines[i])
            i += 1
            
            # Write subtitle text (can be multiple lines)
            while i < len(lines) and lines[i].strip():
                srt.write(lines[i])
                i += 1
            
            # Add empty line after each subtitle
            srt.write("\n")
    
    return srt_file

def generate_short_subtitles(subtitle_file: str) -> str:
    """
    Generate high-impact short video subtitles from a full subtitle file.
    Supports both VTT and SRT formats.
    Returns the path to the generated JSON subtitle file.
    """
    # Ensure the subtitle file exists
    if not os.path.exists(subtitle_file):
        # Try to find the file in the current directory if path is relative
        base_name = os.path.basename(subtitle_file)
        if os.path.exists(base_name):
            subtitle_file = base_name
        else:
            raise FileNotFoundError(f"Subtitle file not found: {subtitle_file}")
    
    print(f"Found subtitle file at: {os.path.abspath(subtitle_file)}")
    
    # Convert VTT to SRT if needed
    if subtitle_file.lower().endswith('.vtt'):
        print("Converting VTT to SRT format...")
        subtitle_file = convert_vtt_to_srt(subtitle_file)
        print(f"Converted to: {subtitle_file}")
    
    # Step 1: Read the subtitle content directly
    with open(subtitle_file, 'r', encoding='utf-8') as f:
        subtitle_content = f.read()
    
    # Step 2: Generate short/high-impact subtitles
    # Create the prompt as a single string
    prompt = """You are a creative subtitle AI focused on generating viral YouTube Shorts 
that grab attention and drive viewers to the full video.

Task: Analyze this entire subtitle file and generate a concise, high-impact version 
for a short video that is not more than 60 seconds long.

Focus on the most shocking, controversial, funny, or exciting parts. 

CRITICAL RULES:
1. Create a COHERENT STORY: Each text must make complete sense on its own AND flow naturally into the next one
2. Be PRECISE with timing:
   - Ensure perfect sync between speech and timing
   - Be exact with timestamps (use milliseconds precision when needed)
3. Output ONLY a JSON array, no other text
4. Each subtitle must be an object with:
   - "start_sec": exact start time in seconds (number, can include decimals)
   - "end_sec": exact end time in seconds (number, can include decimals)
   - "text": exactly what is spoken (string)
5. Maintain natural speech patterns and pauses
6. Condense long speeches while keeping the main idea clear
7. Prioritize the most engaging, emotional, or surprising moments
10. Do NOT add explanations, commentary, or markdown formatting
11. The output should tell a complete, compelling story that makes viewers want to watch the full video

IMPORTANT: The sequence should feel like a natural, engaging narrative that flows from one clip to the next.

Output the JSON array now:"""

    # Create the content parts
    parts = [
        types.Part.from_text(text=subtitle_content),
        types.Part.from_text(text=prompt)
    ]
    
    # Create the content
    content = types.Content(
        role="user",
        parts=parts
    )
    
    # Generate the content
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[content]
    )
    
    # Step 3: Clean and save the JSON output
    output_text = response.text.strip()
    
    # Remove markdown code blocks if present
    if output_text.startswith("```json"):
        output_text = output_text[7:]
    if output_text.startswith("```"):
        output_text = output_text[3:]
    if output_text.endswith("```"):
        output_text = output_text[:-3]
    output_text = output_text.strip()
    
    # Step 4: Parse the JSON (no timing adjustments)
    try:
        # Parse and validate JSON, but don't modify any timings
        subtitles = json.loads(output_text)
        # Convert back to JSON string with consistent formatting
        output_text = json.dumps(subtitles, indent=2)
    except json.JSONDecodeError as e:
        print(f"Warning: Invalid JSON in subtitles: {e}")
    except Exception as e:
        print(f"Warning: Error processing subtitles: {e}")
    
    # Step 5: Save the JSON output
    base_name = os.path.splitext(subtitle_file)[0]
    output_file = f"{base_name}.short.json"
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(output_text)
    
    print("Generated short subtitles:", output_file)
    return output_file
    return output_file