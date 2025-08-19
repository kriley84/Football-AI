from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import os
import requests

app = FastAPI()

API_KEY = os.getenv("API_FOOTBALL_KEY")
API_HOST = "api-football-v1.p.rapidapi.com"

def get_fixtures():
    url = f"https://{API_HOST}/v3/fixtures"
    query = {"league": "39", "season": "2025", "next": "5"}  # 39 = EPL
    headers = {
        "x-rapidapi-host": API_HOST,
        "x-rapidapi-key": API_KEY
    }
    r = requests.get(url, headers=headers, params=query)
    data = r.json()

    # Log API response in Render logs
    print("API response:", data)

    fixtures = []
    for match in data.get("response", []):
        fixtures.append({
            "home": match["teams"]["home"]["name"],
            "away": match["teams"]["away"]["name"],
            "date": match["fixture"]["date"]
        })
    return fixtures

@app.get("/test", response_class=HTMLResponse)
def test():
    fixtures = get_fixtures()
    if not fixtures:
        return HTMLResponse("<h2>No fixtures found (check API key or season year)</h2>")
    
    html = "<h1>Upcoming Premier League Fixtures</h1><ul>"
    for f in fixtures:
        html += f"<li>{f['home']} vs {f['away']} ({f['date']})</li>"
    html += "</ul>"
    return HTMLResponse(html)

@app.get("/")
def home():
    return {"message": "Go to /test to check EPL fixtures"}
