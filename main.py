from fastapi import FastAPI, Query
import pandas as pd

app = FastAPI(title="Premier League Accumulator AI (Static + xG)")

fixtures_data = [
    {"home": "Liverpool", "away": "Bournemouth", "home_win": 72, "draw": 18, "away_win": 10, "home_form": "W W W D W", "away_form": "L D W L L", "home_xg": 2.3, "away_xg": 1.1},
    {"home": "Manchester City", "away": "Newcastle", "home_win": 68, "draw": 20, "away_win": 12, "home_form": "W D W W W", "away_form": "W W L D W", "home_xg": 2.4, "away_xg": 1.6},
    {"home": "Arsenal", "away": "Chelsea", "home_win": 57, "draw": 26, "away_win": 17, "home_form": "W W L W D", "away_form": "D L W L W", "home_xg": 2.1, "away_xg": 1.5},
    {"home": "Tottenham", "away": "Brighton", "home_win": 62, "draw": 22, "away_win": 16, "home_form": "W L W W L", "away_form": "D W W L L", "home_xg": 2.0, "away_xg": 1.6},
    {"home": "West Ham", "away": "Everton", "home_win": 48, "draw": 30, "away_win": 22, "home_form": "L W L D W", "away_form": "D L L W D", "home_xg": 1.6, "away_xg": 1.4},
    {"home": "Aston Villa", "away": "Crystal Palace", "home_win": 59, "draw": 28, "away_win": 13, "home_form": "W D W W L", "away_form": "L L D W D", "home_xg": 1.9, "away_xg": 1.3},
    {"home": "Manchester United", "away": "Fulham", "home_win": 66, "draw": 21, "away_win": 13, "home_form": "W W D W L", "away_form": "L D W L W", "home_xg": 2.0, "away_xg": 1.3},
    {"home": "Brentford", "away": "Nottingham Forest", "home_win": 54, "draw": 29, "away_win": 17, "home_form": "L D W L W", "away_form": "W L L D W", "home_xg": 1.7, "away_xg": 1.4},
    {"home": "Sheffield United", "away": "Luton Town", "home_win": 44, "draw": 33, "away_win": 23, "home_form": "L L D W L", "away_form": "D L W L D", "home_xg": 1.2, "away_xg": 1.1},
    {"home": "Burnley", "away": "Wolves", "home_win": 42, "draw": 34, "away_win": 24, "home_form": "W L L D L", "away_form": "W D W L D", "home_xg": 1.3, "away_xg": 1.4},
]

fixtures_df = pd.DataFrame(fixtures_data)

def badge(prob):
    if prob >= 60: return f"green({prob}%)"
    elif prob >= 40: return f"orange({prob}%)"
    return f"red({prob}%)"

def form_points(form_str):
    pts = 0
    for t in form_str.split():
        if t == "W": pts += 3
        elif t == "D": pts += 1
    return pts

def xg_share(xg_for, xg_against):
    total = xg_for + xg_against
    return xg_for / total if total else 0

def leg_score(win_prob, xg_for, xg_against, form_str):
    return 0.60*win_prob + 0.25*(xg_share(xg_for, xg_against)*100) + 0.15*((form_points(form_str)/15)*100)

@app.get("/fixtures")
def get_fixtures():
    results = []
    for _, r in fixtures_df.iterrows():
        results.append({"fixture": f"{r['home']} vs {r['away']}", "team": r["home"], "rating_color": badge(r["home_win"]), "win_probability": r["home_win"], "draw_probability": r["draw"], "lose_probability": r["away_win"], "xg_for": r["home_xg"], "xg_against": r["away_xg"], "form": r["home_form"]})
        results.append({"fixture": f"{r['home']} vs {r['away']}", "team": r["away"], "rating_color": badge(r["away_win"]), "win_probability": r["away_win"], "draw_probability": r["draw"], "lose_probability": r["home_win"], "xg_for": r["away_xg"], "xg_against": r["home_xg"], "form": r["away_form"]})
    return results

@app.get("/recommendations")
def get_recommendations(n_legs: int = 4):
    ranked = []
    for _, r in fixtures_df.iterrows():
        ranked.append((leg_score(r["home_win"], r["home_xg"], r["away_xg"], r["home_form"]), r))
    ranked.sort(key=lambda x: x[0], reverse=True)
    top = [r for _, r in ranked[:n_legs]]
    results = []
    for r in top:
        results.append({"fixture": f"{r['home']} vs {r['away']}", "team": r["home"], "score": round(leg_score(r["home_win"], r["home_xg"], r["away_xg"], r["home_form"]),1), "rating_color": badge(r["home_win"])})
    return results
