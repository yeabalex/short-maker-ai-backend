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
