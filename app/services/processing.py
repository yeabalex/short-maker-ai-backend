import os
import uuid
import re
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.utils import extract_timestamps_from_srt, parse_json_safely, generate_karaoke_ass_file

def cut_and_merge(input_video: str, timestamps: list, output_name: str = "final_output.mp4") -> Optional[str]:
    """
    Cut and merge video segments based on timestamps with smooth transitions and karaoke-style subtitles.
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
    
    # Generate ASS subtitle file for karaoke-style captions
    ass_file = work_dir / "subtitles.ass"
    print("Generating karaoke-style subtitles...")
    generate_karaoke_ass_file(timestamps, str(ass_file), video_width=1080, video_height=1920)
    print(f"Generated ASS subtitle file: {ass_file}")
        
    clip_names = []
    durations = []
        
    # 1. Cut, Crop, and Add Subtitles to Clips
    for i, ts in enumerate(timestamps, start=1):
        clip_name = f"clip_{i}.mp4"
        clip_path = clips_dir / clip_name
        clip_names.append(clip_name)
        
        duration = ts["end_sec"] - ts["start_sec"]
        durations.append(duration)
        
        # Calculate the subtitle offset for this specific clip
        # Since we're cutting from start_sec to end_sec, we need to adjust subtitle timing
        subtitle_offset = ts["start_sec"]

        subprocess.run([
            "ffmpeg",
            "-y",
            "-i", input_video,
            "-ss", str(ts["start_sec"]),
            "-to", str(ts["end_sec"]),
            "-vf", f"crop=trunc(ih*9/16/2)*2:ih,ass={str(ass_file).replace('\\', '/')}:fontsdir=/Windows/Fonts",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "18",
            "-preset", "slow",
            "-c:a", "aac",
            "-b:a", "192k",
            str(clip_path)
        ], check=True)
                
    output_path = work_dir / output_name
        
    # 2. Merge with Transitions
    if len(clip_names) == 1:
        # Simple copy for single clip
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(clips_dir / clip_names[0]),
            "-c", "copy",
            str(output_path)
        ], check=True)
        
    else:
        # Calculate safe transition duration
        min_dur = min(durations)
        # Target 0.75s, but ensure we don't consume more than half a clip
        trans_dur = min(0.75, min_dur / 2.1)
        
        inputs = []
        for name in clip_names:
            inputs.extend(["-i", name])
            
        filter_complex = ""
        
        # Initial state
        prev_v = "0:v"
        prev_a = "0:a"
        current_offset = durations[0] - trans_dur
        
        for i in range(1, len(clip_names)):
            next_v = f"{i}:v"
            next_a = f"{i}:a"
            out_v = f"v{i}" if i < len(clip_names) - 1 else "outv"
            out_a = f"a{i}" if i < len(clip_names) - 1 else "outa"
            
            # Xfade (video)
            filter_complex += f"[{prev_v}][{next_v}]xfade=transition=fade:duration={trans_dur}:offset={current_offset}[{out_v}];"
            
            # Acrossfade (audio)
            filter_complex += f"[{prev_a}][{next_a}]acrossfade=d={trans_dur}[{out_a}];"
            
            prev_v = out_v
            prev_a = out_a
            current_offset += durations[i] - trans_dur
            
        # Remove trailing semicolon
        filter_complex = filter_complex.rstrip(";")
        
        cmd = [
            "ffmpeg",
            "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-map", "[outa]",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "18",
            "-preset", "slow",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_path)
        ]
        
        subprocess.run(cmd, cwd=str(clips_dir), check=True)

    return str(output_path)

def process_downloaded_video():
    """Process a downloaded video using pre-generated short subtitles."""
    
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
                    
        print(f"Loaded {len(timestamps)} timestamps from short subtitles")
        
        # Trim start and end to avoid "dead air" or unwanted transitions as requested
        # "not take the last seconds of the last clip and the first secons of the comming clip"
        # Timestamps are used as-is, without any addition or subtraction
        pass
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
