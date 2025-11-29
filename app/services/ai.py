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
    
    # Step 2: Generate ONE continuous segment as a SINGLE JSON object with word-level timestamps
    # Create the prompt as a single string
    prompt = """You are a master video editor and storyteller. Your goal is to extract a single, viral-worthy short segment (30-60 seconds) from a longer video's subtitles.

🎯 CORE OBJECTIVE: FIND A COMPLETE NARRATIVE ARC
You must find a segment that stands alone as a complete story or concept. It must have a clear beginning, a middle, and a definitive end.

🚫 STRICT PROHIBITIONS (DO NOT IGNORE):
1.  **NO MID-THOUGHT STARTS**:
    -   NEVER start with conjunctions: "and", "but", "so", "because", "or".
    -   NEVER start with dependent clauses: "which is why...", "that means...".
    -   NEVER start with pronouns (he, she, it, they) unless the antecedent is immediately clear within the first sentence.
    -   NEVER start in the middle of a sentence.

2.  **NO ABRUPT ENDINGS**:
    -   NEVER end in the middle of a sentence.
    -   NEVER end while an idea is still being explained.
    -   The segment MUST end on a period, question mark, or exclamation point that concludes the thought.

✅ SELECTION CRITERIA:
1.  **The Hook (0-5s)**: The first sentence must be engaging and establish the topic immediately. It should grab the viewer's attention.
2.  **The Body**: The middle section should develop the idea or tell the story.
3.  **The Resolution**: The final sentence must wrap up the specific point or story. It should feel like a satisfying conclusion.
4.  **Context Independence**: The viewer must understand what is happening without seeing the rest of the video.

📝 EXAMPLES:

❌ BAD SELECTION (Do NOT do this):
Start: "and that's why he went to the store." (Who is he? Why does it start with 'and'?)
End: "so he bought the..." (Cut off mid-sentence)

✅ GOOD SELECTION:
Start: "Steve Jobs had a unique way of negotiating." (Clear subject, interesting hook)
Body: [Details about the negotiation]
End: "And that is how he got the deal signed." (Conclusive ending)

⚠️ TIMING ACCURACY IS CRITICAL:
-   You MUST copy the EXACT timestamps from the source file.
-   Do not approximate.
-   Verify that the text you selected matches the timestamps exactly.

🚨 TIMING RULES (FOLLOW EXACTLY):

1. **FIND THE SEGMENT FIRST**:
   - Read through the ENTIRE subtitle file
   - Identify the most engaging 30-60 second continuous portion that follows the NARRATIVE ARC rules above.
   - Note the EXACT start time of the first line
   - Note the EXACT end time of the last line

2. **COPY EXACT TIMESTAMPS**:
   - Look at the subtitle file timestamps (format: HH:MM:SS,MMM)
   - Convert to seconds PRECISELY
   - Example: 00:00:52.960 = 52.960 seconds (NOT 52.96, NOT 53.0)
   - Example: 00:01:23.680 = 83.680 seconds (NOT 83.68, NOT 84.0)

3. **VERIFY YOUR SELECTION**:
   - Read the text content between your start and end times
   - Make ABSOLUTELY SURE the text matches what you're outputting
   - If start=52.960 and end=84.0, the text MUST be exactly what's spoken from 52.960s to 84.0s
   - NO GUESSING, NO APPROXIMATING

📊 WORD-LEVEL TIMING:

- Break down the combined text into individual words
- Estimate word timing proportionally based on subtitle line durations
- Each word needs: "word" (text), "start" (seconds), "end" (seconds)

📤 OUTPUT FORMAT:

[
  {
    "start_sec": <EXACT start time from subtitle file in seconds>,
    "end_sec": <EXACT end time from subtitle file in seconds>,
    "text": "<ALL text from that time range combined>",
    "words": [
      {"word": "<word1>", "start": <time>, "end": <time>},
      {"word": "<word2>", "start": <time>, "end": <time>},
      ... (all words from the entire segment)
    ]
  }
]

⚠️ FINAL WARNING:
If the text in your output does NOT match the actual spoken content at those timestamps, the video will be BROKEN.
DOUBLE-CHECK your timestamps before outputting!

🎬 NOW: Output ONE JSON object with EXACT timing for ONE continuous 30-60 second segment that tells a COMPLETE STORY:"""
    
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
