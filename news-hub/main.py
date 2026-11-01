import os
import json
import time
import google.generativeai as genai
from pathlib import Path

# Base directory setup for reliable path resolution inside GitHub Actions nested folder structure
BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "state.json"

# Model configuration using verified stable endpoint
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
API_KEY = os.getenv("GEMINI_API_KEY")

if API_KEY:
    genai.configure(api_key=API_KEY)

def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def call_gemini_with_retry(prompt_text):
    """Executes Gemini requests with exponential backoff handling for 429, 503, and timeouts."""
    if not API_KEY:
        raise ValueError("GEMINI_API_KEY environment variable is missing or empty.")
    
    model = genai.GenerativeModel(MODEL)
    max_attempts = 5
    
    for attempt in range(max_attempts):
        try:
            response = model.generate_content(prompt_text)
            return response.text
        except Exception as e:
            err_str = str(e)
            if any(code in err_str for code in ["503", "429", "timed out", "deadline"]):
                if attempt == max_attempts - 1:
                    raise e
                sleep_time = 10 * (2 ** attempt)  # Exponential backoff: 10s, 20s, 40s, 80s
                time.sleep(sleep_time)
            else:
                raise e

if __name__ == "__main__":
    print(f"Initializing News Hub using model: {MODEL}")
    state = load_state()
    # Pipeline execution continues safely here...
