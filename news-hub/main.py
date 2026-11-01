import os
import json
import requests
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai

# Load environment variables with strip to prevent any trailing spaces or newlines
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
FB_PAGE_ID = os.environ.get("FB_PAGE_ID", "").strip()
FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN", "").strip()

print("Initializing News Hub...")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is missing from environment variables.")

genai.configure(api_key=GEMINI_API_KEY)
model_name = "gemini-3.8-flash"
print(f"Using Gemini model: {model_name}")

def load_state():
    state_file = os.path.join(os.path.dirname(__file__), "state.json")
    if os.path.exists(state_file):
        try:
            with open(state_file, "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    if "processed_links" not in data:
                        data["processed_links"] = []
                    return data
        except Exception as e:
            print(f"Error loading state.json: {e}")
    return {"processed_links": []}

def save_state(state):
    state_file = os.path.join(os.path.dirname(__file__), "state.json")
    try:
        with open(state_file, "w") as f:
            json.dump(state, f, indent=4)
        print("State updated successfully.")
    except Exception as e:
        print(f"Error saving state.json: {e}")

def fetch_latest_news():
    print("Fetching latest news...")
    return {
        "title": "Major Tech Breakthrough in AI Automation",
        "link": "https://example.com/ai-news-1",
        "summary": "New advancements in automated workflows are transforming how digital news hubs operate globally."
    }

def generate_poster(news_item):
    print("Generating branded news poster...")
    width, height = 1200, 630
    image = Image.new("RGB", (width, height), color=(15, 23, 42))
    draw = ImageDraw.Draw(image)
    
    try:
        font_title = ImageFont.load_default()
    except Exception:
        font_title = None

    draw.text((50, 80), "BREAKING NEWS", fill=(239, 68, 68), font=font_title)
    draw.text((50, 150), news_item["title"], fill=(255, 255, 255), font=font_title)
    
    poster_path = os.path.join(os.path.dirname(__file__), "output_poster.png")
    image.save(poster_path)
    print(f"Poster saved locally at: {poster_path}")
    return poster_path

def post_to_facebook(news_item, poster_path):
    if not FB_PAGE_ID or not FB_PAGE_TOKEN:
        print("Facebook credentials missing. Skipping posting.")
        return

    print("Posting to Facebook page...")
    url = f"https://graph.facebook.com/v18.0/{FB_PAGE_ID}/photos"
    caption = f"{news_item['title']}\n\n{news_item['summary']}\n\nRead more: {news_item['link']}"
    
    with open(poster_path, "rb") as image_file:
        files = {'source': image_file}
        data = {'caption': caption, 'access_token': FB_PAGE_TOKEN}
        response = requests.post(url, data=data, files=files)
        
        if response.status_code == 200:
            print("Successfully posted to Facebook!")
        else:
            print(f"Failed to post to Facebook: {response.text}")

def main():
    print("Starting news pipeline execution...")
    state = load_state()
    
    news = fetch_latest_news()
    if not news:
        print("No new stories found.")
        return

    if news["link"] in state.get("processed_links", []):
        print("News item already processed. Skipping.")
        return

    # Generate visual poster
    poster_path = generate_poster(news)

    # Publish to Facebook
    post_to_facebook(news, poster_path)

    # Update state safely
    if "processed_links" not in state:
        state["processed_links"] = []
    state["processed_links"].append(news["link"])
    save_state(state)
    print("Pipeline execution completed successfully.")

if __name__ == "__main__":
    main()
