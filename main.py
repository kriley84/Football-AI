from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="Football Accumulator AI")

# Sample data
fixtures_data = [
    {"home": "Liverpool", "away": "Bournemouth", "win%": 73.1},
    {"home": "Manchester City", "away": "Newcastle", "win%": 68.8},
    {"home": "Manchester United", "away": "Fulham", "win%": 64.8},
    {"home": "Aston Villa", "away": "Crystal Palace", "win%": 60.2},
    {"home": "Everton", "away": "Brighton", "win%": 38.4}
]

@app.get("/fixtures")
def get_fixtures():
    """
    Returns the upcoming fixtures as JSON (API use).
    """
    return {"fixtures": fixtures_data}

@app.get("/recommendations", response_class=HTMLResponse)
def get_recommendations():
    """
    Returns HTML table with color-coded recommendations.
    """
    html_content = """
    <html>
    <head>
        <style>
            table { border-collapse: collapse; width: 60%; margin: 20px auto; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: center; font-family: Arial; }
            th { background-color: #333; color: white; }
            .green { background-color: #4CAF50; color: white; }
            .orange { background-color: #FF9800; color: white; }
            .red { background-color: #F44336; color: white; }
        </style>
    </head>
    <body>
        <h2 style="text-align:center;">Premier League Recommendations</h2>
        <table>
            <tr>
                <th>Fixture</th>
                <th>Win %</th>
                <th>Rating</th>
            </tr>
    """

    for f in fixtures_data:
        if f["win%"] >= 60:
            color_class = "green"
        elif 40 <= f["win%"] < 60:
            color_class = "orange"
        else:
            color_class = "red"

        html_content += f"""
            <tr>
                <td>{f['home']} vs {f['away']}</td>
                <td>{f['win%']:.1f}%</td>
                <td class="{color_class}">{color_class.capitalize()}</td>
            </tr>
        """

    html_content += """
        </table>
    </body>
    </html>
    """

    return HTMLResponse(content=html_content)
