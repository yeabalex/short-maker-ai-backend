import os
import json
from google import genai
from google.genai import types
from app.utils import convert_vtt_to_srt
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

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
    prompt = """You are a precision-focused AI video editor assistant.

Task: Create a viral YouTube Short (< 60s) from this subtitle file.

CRITICAL INSTRUCTION ON TIMINGS:
You must be EXTREMELY ACCURATE with timestamps. 
1.  **REVIEW** every selected line against the original subtitle file.
2.  **COPY** the exact `start_sec` and `end_sec` from the original file for the selected text.
3.  **DO NOT** approximate or guess. If a sentence starts at 00:00:05.123, your output MUST be 5.123.
4.  Ensure there is NO OVERLAP between clips unless they are continuous in the original video.

Content Guidelines:
- Select the most shocking, controversial, funny, or exciting parts.
- Create a COHERENT STORY. The clips must flow naturally.
- Maintain natural speech patterns.

Output Format:
- Return ONLY a JSON array.
- Each object must have:
   - "start_sec": exact start time in seconds (number, e.g., 12.345)
   - "end_sec": exact end time in seconds (number, e.g., 15.678)
   - "text": exact spoken text (string)

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
