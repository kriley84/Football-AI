from fastapi import FastAPI
import requests
import os

app = FastAPI()

# Get API key from environment variable on Render OR hardcode for testing
API_KEY = os.getenv("API_FOOTBALL_KEY", "your_real_api_key_here")

app.get("/")
def home():
    return {"message": "Go to /fixtures to check EPL fixtures"}

@app.get("/fixtures")
def get_fixtures():
    url = "https://v3.football.api-sports.io/fixtures"
    headers = {"x-apisports-key": API_KEY}
    params = {"league": 39, "season": 2025}  # EPL 2025/26 season

    response = requests.get(url, headers=headers, params=params)
    
    # Return the full raw response so we can debug
    try:
        return response.json()
    except Exception:
        return {"error": "Could not parse response", "text": response.text}
