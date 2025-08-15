from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import requests
import os

app = FastAPI()

API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY")  # Set this in Render Environment Variables

def get_live_fixtures():
    """Fetch next 10 Premier League fixtures from API-Football"""
    url = "https://api-football-v1.p.rapidapi.com/v3/fixtures"
    querystring = {"league": "39", "season": "2025", "next": "10"}  # 39 = EPL
    headers = {
        "x-rapidapi-host": "api-football-v1.p.rapidapi.com",
        "x-rapidapi-key": API_FOOTBALL_KEY
    }
    response = requests.get(url, headers=headers, params=querystring)

    if response.status_code != 200:
        print(f"API error: {response.status_code}")
        return []

    data = response.json()
    fixtures = []
    for f in data["response"]:
        home = f["teams"]["home"]["name"]
        away = f["teams"]["away"]["name"]

        # Placeholder probability (replace later with real odds/xG logic)
        win_pct = 60.0 if f["teams"]["home"]["winner"] is True else 40.0

        fixtures.append({
            "fixture": f"{home} vs {away}",
            "team": home,
            "score": win_pct
        })
    return fixtures


def get_rating_color(score):
    """Return color and score text based on win probability"""
    if score < 40:
        return f"<td style='background-color:red;color:white;text-align:center;'>{score:.0f}%</td>"
    elif 40 <= score <= 60:
        return f"<td style='background-color:orange;color:black;text-align:center;'>{score:.0f}%</td>"
    else:
        return f"<td style='background-color:green;color:white;text-align:center;'>{score:.0f}%</td>"


@app.get("/fixtures", response_class=HTMLResponse)
def fixtures():
    fixtures_data = get_live_fixtures()
    html = "<h1>Premier League Fixtures</h1><table border='1'><tr><th>Fixture</th><th>Team</th><th>Win %</th></tr>"
    for match in fixtures_data:
        html += f"<tr><td>{match['fixture']}</td><td>{match['team']}</td>{get_rating_color(match['score'])}</tr>"
    html += "</table>"
    return html


@app.get("/recommendations", response_class=HTMLResponse)
def recommendations():
    fixtures_data = get_live_fixtures()
    html = "<h1>Recommended Picks</h1><table border='1'><tr><th>Fixture</th><th>Team</th><th>Win %</th></tr>"
    for match in fixtures_data:
        if match['score'] >= 60:  # Example: only recommend high-probability wins
            html += f"<tr><td>{match['fixture']}</td><td>{match['team']}</td>{get_rating_color(match['score'])}</tr>"
    html += "</table>"
    return html
