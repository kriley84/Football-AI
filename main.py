import os
import math
import requests
from flask import Flask, jsonify, Response

# ========== CONFIG ==========
API_HOST = "api-football-v1.p.rapidapi.com"
API_KEY = os.getenv("API_FOOTBALL_KEY")  # set in Render -> Environment
DEFAULT_LEAGUE = 39                      # EPL
DEFAULT_SEASON = 2025                    # 2025/26 = 2025
NEXT_FIXTURES = 8                        # how many upcoming matches to score

# Weights you can tweak
W_ODDS = 0.70      # bookmaker market baseline
W_FORM = 0.10      # recent form boost/penalty
W_TABLE = 0.06     # league table gap
W_H2H = 0.05       # head-to-head last N
W_GOALS = 0.05     # GF/GA per match delta
W_INJ = 0.04       # injuries / suspensions
W_XG = 0.00        # set >0 if your plan exposes xG reliably

HEADERS = {
    "x-rapidapi-host": API_HOST,
    "x-rapidapi-key": API_KEY or ""
}

app = Flask(__name__)

# ---------- helpers ----------
def api_get(path, params):
    """GET helper with basic error tolerance."""
    url = f"https://{API_HOST}{path}"
    r = requests.get(url, headers=HEADERS, params=params, timeout=20)
    try:
        data = r.json()
    except Exception:
        return {"errors": {"parse": r.text}}, 500
    return data, r.status_code

def implied_pct(decimal_odds):
    try:
        o = float(decimal_odds)
        if o <= 1.0:
            return None
        return 100.0 / o
    except Exception:
        return None

def color_for_pct(p):
    if p is None:
        return "gray"
    if p < 40:
        return "red"
    if p <= 60:
        return "orange"
    return "green"

def percent(x):
    return f"{x:.1f}%" if x is not None else "—"

def clamp01(x):
    return max(0.0, min(100.0, x))

# ---------- data pulls ----------
def get_next_fixtures(league=DEFAULT_LEAGUE, season=DEFAULT_SEASON, n=NEXT_FIXTURES):
    params = {"league": league, "season": season, "next": n}
    data, _ = api_get("/v3/fixtures", params)
    return data.get("response", [])

def get_odds_for_fixture(fixture_id):
    # Bet365 (bookmaker id 8) 1X2 market is typical; fall back to first bookmaker if needed
    params = {"fixture": fixture_id}
    data, _ = api_get("/v3/odds", params)
    resp = data.get("response", [])
    if not resp:
        return None
    # try to find a "Match Winner" or "1X2" market
    for bk in resp[0].get("bookmakers", []):
        for bet in bk.get("bets", []):
            name = bet.get("name", "").lower()
            if "match winner" in name or "1x2" in name:
                # -> values: label: "Home"/"Draw"/"Away" or team names
                out = {}
                for v in bet.get("values", []):
                    out[v.get("label")] = v.get("odd")
                return out
    return None

def get_team_stats(league, season, team_id):
    params = {"league": league, "season": season, "team": team_id}
    data, _ = api_get("/v3/teams/statistics", params)
    return data.get("response", {})

def get_injuries(fixture_id=None, team_id=None, season=None):
    params = {}
    if fixture_id:
        params["fixture"] = fixture_id
    if team_id:
        params["team"] = team_id
    if season:
        params["season"] = season
    data, _ = api_get("/v3/injuries", params)
    return data.get("response", [])

def get_h2h(home_id, away_id, last=5):
    params = {"h2h": f"{home_id}-{away_id}", "last": last}
    data, _ = api_get("/v3/fixtures/headtohead", params)
    return data.get("response", [])

# ---------- feature engineering ----------
def form_score(form_str):
    # API returns form like "WWDLW" (sometimes includes null); score W=1, D=0.5, L=0
    if not form_str:
        return 0.0
    m = {"W": 1.0, "D": 0.5, "L": 0.0}
    vals = [m.get(c, 0) for c in form_str[-5:]]
    return sum(vals) / max(1, len(vals))  # 0..1

def table_gap_score(rank_home, rank_away):
    if not rank_home or not rank_away:
        return 0.0
    # negative when home lower rank number (better team) -> boost home
    gap = (rank_away or 20) - (rank_home or 20)  # positive if home ranked better
    # scale to -1..1 approximately
    return max(-1, min(1, gap / 10.0))

def goals_delta(gf_home, ga_home, gf_away, ga_away):
    # average goals scored minus conceded per match (per team), take difference
    try:
        home_net = (gf_home - ga_home)
        away_net = (gf_away - ga_away)
        delta = home_net - away_net
        return max(-2, min(2, delta)) / 2.0  # normalize to -1..1
    except Exception:
        return 0.0

def h2h_score(h2h_matches, home_id):
    # simple: +1 for each home win, +0.5 draw, 0 for loss in last N; normalize 0..1 then map around 0
    if not h2h_matches:
        return 0.0
    s = 0.0
    for m in h2h_matches:
        try:
            h_id = m["teams"]["home"]["id"]
            home_winner = m["teams"]["home"]["winner"]
            away_winner = m["teams"]["away"]["winner"]
            if home_winner is True:
                s += 1.0 if h_id == home_id else 0.0
            elif away_winner is True:
                s += 0.0 if h_id == home_id else 1.0
            else:
                s += 0.5
        except Exception:
            pass
    avg = s / (len(h2h_matches) or 1)  # 0..1
    return (avg - 0.5) * 2.0  # map to -1..1 around 0
def injuries_penalty(inj_list, is_home=True):
    # crude: penalty grows with number of injured; if many defenders/midfielders, penalize more
    try:
        n = len(inj_list)
        return min(0.10, n * 0.01) * (1 if is_home else 1)  # up to -10%
    except Exception:
        return 0.0

# ---------- main scoring ----------
def score_fixture(fx, league, season):
    """
    Build a composite probability for Home/Draw/Away using:
    odds (baseline) + form + table + h2h + goals + injuries (+ xG when available).
    """
    fixture_id = fx["fixture"]["id"]
    home = fx["teams"]["home"]; away = fx["teams"]["away"]
    home_id, away_id = home["id"], away["id"]
    home_name, away_name = home["name"], away["name"]

    # --- baseline from odds ---
    odds = get_odds_for_fixture(fixture_id) or {}
    # labels can be "Home"/"Draw"/"Away" or actual team names; support both:
    home_odds = odds.get("Home") or odds.get(home_name)
    draw_odds = odds.get("Draw")
    away_odds = odds.get("Away") or odds.get(away_name)
    p_home = implied_pct(home_odds) if home_odds else None
    p_draw = implied_pct(draw_odds) if draw_odds else None
    p_away = implied_pct(away_odds) if away_odds else None

    # If odds missing, start balanced
    if p_home is None or p_away is None or p_draw is None:
        p_home = p_home or 33.3
        p_draw = p_draw or 33.3
        p_away = p_away or 33.3

    # normalize to 100
    total = p_home + p_draw + p_away
    p_home, p_draw, p_away = [x * 100.0 / total for x in (p_home, p_draw, p_away)]

    # --- enrichers ---
    stats_home = get_team_stats(league, season, home_id) or {}
    stats_away = get_team_stats(league, season, away_id) or {}

    # form (0..1)
    f_home = form_score(stats_home.get("form"))
    f_away = form_score(stats_away.get("form"))
    form_adj = (f_home - f_away)  # -1..1

    # table rank (1 better)
    r_home = stats_home.get("league", {}).get("rank")
    r_away = stats_away.get("league", {}).get("rank")
    table_adj = table_gap_score(r_home, r_away)  # -1..1

    # goals per match
    gh = stats_home.get("goals", {}).get("for", {}).get("average", {}).get("total")
    ch = stats_home.get("goals", {}).get("against", {}).get("average", {}).get("total")
    ga = stats_away.get("goals", {}).get("for", {}).get("average", {}).get("total")
    ca = stats_away.get("goals", {}).get("against", {}).get("average", {}).get("total")
    try:
        gh, ch, ga, ca = float(gh or 0), float(ch or 0), float(ga or 0), float(ca or 0)
    except Exception:
        gh = ch = ga = ca = 0.0
    goals_adj = goals_delta(gh, ch, ga, ca)  # -1..1

    # head-to-head last 5
    h2h = get_h2h(home_id, away_id, last=5)
    h2h_adj = h2h_score(h2h, home_id)  # -1..1

    # injuries (fixture or team)
    inj_home = get_injuries(team_id=home_id, season=season)
    inj_away = get_injuries(team_id=away_id, season=season)
    inj_adj_home = -injuries_penalty(inj_home, True)      # negative for home if injuries
    inj_adj_away = -injuries_penalty(inj_away, False)

    # xG hook (if present in your plan, put it into stats_home/stats_away parsing and set W_XG > 0)
    xg_adj = 0.0

    # --- combine into a single delta to tilt the home/draw/away ---
    # Build a home-tilt in range roughly -1..1, then map to percentage redistribution.
    tilt = (
        W_FORM * form_adj +
        W_TABLE * table_adj +
        W_GOALS * goals_adj +
        W_H2H * h2h_adj +
        W_INJ * (inj_adj_home - inj_adj_away) +
        W_XG * xg_adj
    )
    # limit tilt so we don't go crazy
    tilt = max(-0.5, min(0.5, tilt))  # -0.5..0.5

    # Apply tilt around the odds baseline (only to home/away; keep draw stable but slightly adjusted)
    ph = clamp01(p_home * (1 + tilt))
    pa = clamp01(p_away * (1 - tilt))
    # keep draw proportionate so sums to 100
    pd = clamp01(max(0.0, 100.0 - (ph + pa)))

    # Renormalize to 100 if roundoff drift
    s = ph + pd + pa
    if s > 0:
        ph, pd, pa = [x * 100.0 / s for x in (ph, pd, pa)]

    rec = {
        "fixture_id": fixture_id,
        "kickoff": fx["fixture"]["date"],
        "home": {"id": home_id, "name": home_name},
        "away": {"id": away_id, "name": away_name},
        "baseline": {"home": p_home, "draw": p_draw, "away": p_away},
        "adjusted": {"home": ph, "draw": pd, "away": pa},
        "colors": {
            "home": color_for_pct(ph),
            "draw": color_for_pct(pd),
            "away": color_for_pct(pa)
        },
        "features": {
            "form_home": f_home, "form_away": f_away,
            "rank_home": r_home, "rank_away": r_away,
            "goals_avg_home": gh, "concede_avg_home": ch,
            "goals_avg_away": ga, "concede_avg_away": ca,
            "h2h_last5": len(h2h),
            "inj_home_count": len(inj_home), "inj_away_count": len(inj_away),
        }
    }
    return rec

# ---------- routes ----------
@app.route("/")
def root():
    if not API_KEY:
        return "❗ Set API_FOOTBALL_KEY in Render → Environment Variables.", 500
    return "✅ Football AI is live. Try /analyze or /fixtures"

@app.route("/fixtures")
def fixtures_list():
    fxs = get_next_fixtures()
    out = []
    for f in fxs:
        out.append({
            "fixture_id": f["fixture"]["id"],
            "date": f["fixture"]["date"],
            "home": f["teams"]["home"]["name"],
            "away": f["teams"]["away"]["name"],
        })
    return jsonify(out)

@app.route("/analyze")
def analyze_html():
    fxs = get_next_fixtures()
    if not fxs:
        return Response("<h2>No fixtures found (check key/season/league)</h2>", mimetype="text/html")
    rows = []
    for f in fxs:
        rec = score_fixture(f, DEFAULT_LEAGUE, DEFAULT_SEASON)
        match = f"{rec['home']['name']} vs {rec['away']['name']}"
        home_cell = f"<td style='background:{rec['colors']['home']};color:white;text-align:center'>{percent(rec['adjusted']['home'])}</td>"
        draw_cell = f"<td style='background:{rec['colors']['draw']};color:white;text-align:center'>{percent(rec['adjusted']['draw'])}</td>"
        away_cell = f"<td style='background:{rec['colors']['away']};color:white;text-align:center'>{percent(rec['adjusted']['away'])}</td>"
        rows.append(f"<tr><td>{match}</td><td>{rec['kickoff']}</td>{home_cell}{draw_cell}{away_cell}</tr>")
    html = f"""
    <html><head><title>EPL Recommendations</title>
    <style>table{{border-collapse:collapse;width:95%;margin:20px auto}}
    th,td{{border:1px solid #ccc;padding:8px;text-align:center;font-family:Arial}}</style>
    </head><body>
    <h2 style="text-align:center">Premier League {DEFAULT_SEASON}/{str(DEFAULT_SEASON+1)[-2:]} — Recommendations</h2>
    <table>
      <tr><th>Fixture</th><th>Kickoff</th><th>Home</th><th>Draw</th><th>Away</th></tr>
      {''.join(rows)}
    </table>
    <p style="text-align:center;font-size:12px;color:#666">
      Baseline from odds, adjusted by form, league rank, H2H, goals & injuries.
    </p>
    </body></html>
    """
    return Response(html, mimetype="text/html")

@app.route("/debug/<int:fixture_id>")
def debug_fixture(fixture_id):
    # find fixture in the next batch or fetch by id
    data, _ = api_get("/v3/fixtures", {"id": fixture_id})
    resp = data.get("response", [])
    if not resp:
        return jsonify({"error": "fixture not found"})
    rec = score_fixture(resp[0], DEFAULT_LEAGUE, DEFAULT_SEASON)
    return jsonify(rec)

if __name__ == "__main__":
    # Flask dev server (Render will use gunicorn; see Start Command)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
    @app.route("/debug-key")
def debug_key():
    return {"RAPIDAPI_KEY": os.environ.get("RAPIDAPI_KEY", "NOT SET")}
