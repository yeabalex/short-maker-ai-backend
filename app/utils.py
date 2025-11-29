import re
import json
import os
from typing import List, Dict, Any, Union, Optional

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

def generate_karaoke_ass_file(timestamps: List[Dict[str, Any]], output_path: str, video_width: int = 1080, video_height: int = 1920) -> str:
    """
    Generate an ASS subtitle file with karaoke-style word highlighting.
    Shows 3 words at a time (sliding window) for viral TikTok/YouTube Shorts style.
    
    Args:
        timestamps: List of timestamp dictionaries with 'words' array containing word-level timing
        output_path: Path where the ASS file should be saved
        video_width: Width of the video (default 1080 for vertical videos)
        video_height: Height of the video (default 1920 for vertical videos)
    
    Returns:
        Path to the generated ASS file
    """
    
    # ASS file header with styling
    ass_content = f"""[Script Info]
Title: Karaoke Subtitles
ScriptType: v4.00+
WrapStyle: 0
PlayResX: {video_width}
PlayResY: {video_height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,70,&H00FFFFFF,&H00FFFF00,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,2,5,10,10,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    def format_time(seconds: float) -> str:
        """Convert seconds to ASS timestamp format (H:MM:SS.CS)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centisecs = int((seconds % 1) * 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"
    
    # Generate dialogue lines with sliding window karaoke effects
    for clip in timestamps:
        if 'words' not in clip or not clip['words']:
            # Fallback: if no word-level timing, show entire text
            start_time = format_time(clip['start_sec'])
            end_time = format_time(clip['end_sec'])
            text = clip.get('text', '').replace('\n', ' ')
            ass_content += f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}\n"
            continue
        
        words = clip['words']
        
        # Create sliding window of 3 words at a time
        window_size = 3
        
        i = 0
        while i < len(words):
            # Get the current window of words
            window_words = words[i:i+window_size]
            
            if not window_words:
                break
            
            # Calculate timing for this window
            window_start = window_words[0].get('start', clip['start_sec'])
            window_end = window_words[-1].get('end', clip['end_sec'])
            
            # Build karaoke text for this window
            karaoke_text = ""
            for j, word_data in enumerate(window_words):
                word = word_data.get('word', '')
                word_start = word_data.get('start', window_start)
                word_end = word_data.get('end', window_end)
                
                # Calculate duration in centiseconds for karaoke effect
                duration_cs = int((word_end - word_start) * 100)
                
                # Add karaoke timing tag
                karaoke_text += f"{{\\k{duration_cs}}}{word}"
                
                # Add space between words (except for last word in window)
                if j < len(window_words) - 1:
                    karaoke_text += " "
            
            # Add the dialogue line for this window
            start_time = format_time(window_start)
            end_time = format_time(window_end)
            ass_content += f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{karaoke_text}\n"
            
            # Move to next window (non-overlapping to prevent duplication)
            i += window_size
    
    # Write the ASS file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(ass_content)
    
    return output_path
