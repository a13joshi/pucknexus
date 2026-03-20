"""
nexus_board.py — NexusBoard Data Pipeline
Composite schedule analyzer: schedule + category value + roster + free agents.
Inspired by BasketballMonster's Schedule Analyzer.
"""

import requests
import pandas as pd
from datetime import date, datetime, timedelta
from data_fetcher import get_nhl_schedule, get_fantasy_weeks


# ── Opponent quality: goals allowed per game by team (lower = tougher defense) ──
NHL_TEAM_ID_MAP = {
    1: 'NJD', 2: 'NYI', 3: 'NYR', 4: 'PHI', 5: 'PIT',
    6: 'BOS', 7: 'BUF', 8: 'MTL', 9: 'OTT', 10: 'TOR',
    12: 'CAR', 13: 'FLA', 14: 'TBL', 15: 'WSH', 16: 'CHI',
    17: 'DET', 18: 'NSH', 19: 'STL', 20: 'CGY', 21: 'COL',
    22: 'EDM', 23: 'VAN', 24: 'ANA', 25: 'DAL', 26: 'LAK',
    28: 'SJS', 29: 'CBJ', 30: 'MIN', 52: 'WPG', 53: 'ARI',
    54: 'VGK', 55: 'SEA', 59: 'UTA',
}


def get_team_stats(season="20252026"):
    """
    Fetches team-level stats for opponent quality scoring.
    Returns dict: { team_abbrev: { 'gf_pg', 'ga_pg', 'pp_pct', 'shots_pg' } }
    """
    url = "https://api.nhle.com/stats/rest/en/team/summary"
    params = {
        "isAggregate": "false",
        "isGame": "false",
        "cayenneExp": f"seasonId={season} and gameTypeId=2",
        "sort": '[{"property":"wins","direction":"DESC"}]',
        "limit": 50,
    }
    try:
        resp = requests.get(url, params=params, timeout=15).json()
        team_map = {}
        for row in resp.get('data', []):
            team_id = row.get('teamId')
            abbrev  = NHL_TEAM_ID_MAP.get(team_id)
            if not abbrev:
                continue
            gp = max(row.get('gamesPlayed', 1), 1)
            team_map[abbrev] = {
                'gf_pg':    round(row.get('goalsForPerGame',     0) or 0, 3),
                'ga_pg':    round(row.get('goalsAgainstPerGame', 0) or 0, 3),
                'pp_pct':   round(row.get('powerPlayPct',        0) or 0, 4),
                'shots_pg': round(row.get('shotsForPerGame',     0) or 0, 2),
                'sa_pg':    round(row.get('shotsAgainstPerGame', 0) or 0, 2),
            }
        print(f"📊 Team stats loaded: {len(team_map)} teams")
        return team_map
    except Exception as e:
        print(f"⚠️ Team stats fetch error: {e}")
        return {}


def _ease_score(gp, home_games, b2b_count, opp_ga_avg, league_ga_avg):
    """
    Composite ease score 0–1 (higher = easier/more favorable schedule).
    Factors:
      - Game count (more games = more value)
      - Home advantage (home games worth slightly more)
      - B2B penalty (B2B second games reduce effectiveness)
      - Opponent quality (facing high-GA teams = easier scoring)
    """
    # Game count component (0–1 normalized to max 7 games)
    gp_score = min(gp / 7.0, 1.0)

    # Home advantage (home games = slight boost)
    home_ratio = home_games / max(gp, 1)
    home_score = 0.5 + 0.1 * home_ratio

    # B2B penalty
    b2b_penalty = 1.0 - (b2b_count * 0.08)

    # Opponent quality (facing teams that allow more goals = easier)
    if league_ga_avg > 0:
        opp_score = min(opp_ga_avg / league_ga_avg, 1.5) / 1.5
    else:
        opp_score = 0.5

    raw = (gp_score * 0.40 + home_score * 0.20 + b2b_penalty * 0.20 + opp_score * 0.20)
    return round(min(max(raw, 0.0), 1.0), 3)


def build_nexusboard(
    week_label=None,
    num_days=7,
    evaluated_df=None,
    g_df_global=None,
    yahoo_df=None,
    weights=None,
    cats=None,
    season="20252026",
):
    """
    Main NexusBoard builder. Returns:
      - grid_df: DataFrame with one row per NHL team
      - week_info: dict with start/end/label
      - day_cols: list of date strings in the window
    """
    today = date.today()
    weeks = get_fantasy_weeks()

    # Determine week window
    if week_label == "This Week" or week_label is None:
        current_week = next((w for w in weeks if w['start'] <= today <= w['end']), weeks[0])
    elif week_label == "Next Week":
        current_week = next(
            (w for w in weeks if w['start'] > today),
            weeks[-1]
        )
    elif week_label == "Remaining":
        # Use remaining days this week
        current_week = next((w for w in weeks if w['start'] <= today <= w['end']), weeks[0])
    elif week_label == "Playoffs":
        # Use last 3 weeks
        future = [w for w in weeks if w['start'] > today]
        if len(future) >= 3:
            start = future[-3]['start']
            end = future[-1]['end']
            current_week = {'start': start, 'end': end, 'label': 'Playoffs'}
        else:
            current_week = next((w for w in weeks if w['start'] <= today <= w['end']), weeks[0])
    else:
        current_week = next((w for w in weeks if w['start'] <= today <= w['end']), weeks[0])

    start_date = current_week['start']
    end_date   = current_week['end']

    # For "Remaining", start from today not week start
    if week_label == "Remaining":
        start_date = today

    start_str = str(start_date)
    end_str   = str(end_date)

    week_info = {
        'label': current_week.get('label', f"{start_str} – {end_str}"),
        'start': start_str,
        'end':   end_str,
    }

    # ── Fetch schedule ──────────────────────────────────────────────────────
    sched = get_nhl_schedule(start_str)

    # Build day columns
    day_cols = []
    d = start_date
    while d <= end_date:
        day_cols.append(str(d))
        d += timedelta(days=1)

    # Build per-team game data
    team_games = {}  # team -> {date: {'opp': str, 'home': bool}}
    team_b2b   = {}  # team -> count of B2B second games

    for d_str, games in sched.items():
        if start_str <= d_str <= end_str:
            for team, opp_str in games.items():
                if team not in team_games:
                    team_games[team] = {}
                is_home = opp_str.startswith('vs')
                opp = opp_str.replace('vs ', '').replace('@ ', '').strip()
                team_games[team][d_str] = {'opp': opp, 'home': is_home}

    # Detect B2B (team plays two consecutive days)
    for team, games_dict in team_games.items():
        sorted_dates = sorted(games_dict.keys())
        b2b = 0
        for i in range(1, len(sorted_dates)):
            d1 = datetime.strptime(sorted_dates[i-1], '%Y-%m-%d').date()
            d2 = datetime.strptime(sorted_dates[i], '%Y-%m-%d').date()
            if (d2 - d1).days == 1:
                b2b += 1
        team_b2b[team] = b2b

    # ── Team stats for opponent quality ────────────────────────────────────
    team_stats = get_team_stats(season)
    league_ga_avg = (
        sum(v['ga_pg'] for v in team_stats.values()) / max(len(team_stats), 1)
        if team_stats else 2.8
    )

    # ── Per-category schedule value ─────────────────────────────────────────
    # For each team, compute how favorable their schedule is for each category
    # Based on: opponent GA/game (for scoring cats) and opponent PIM/HIT (for physical cats)
    # Z-score approach: how much above/below average is this team's opponent slate?
    active_cats = cats or ['G', 'A', '+/-', 'PPP', 'SOG', 'HIT', 'BLK']

    # ── Roster + FA mapping ─────────────────────────────────────────────────
    team_my_players = {}   # team -> [player names on my roster]
    team_top_fa     = {}   # team -> [(name, score), ...]

    if yahoo_df is not None and not yahoo_df.empty and evaluated_df is not None and not evaluated_df.empty:
        merged = pd.merge(
            yahoo_df[['name', 'Status', 'Is_Mine', 'match_key']],
            evaluated_df[['Player', 'Team', 'NexusScore', 'match_key']],
            on='match_key', how='inner'
        )

        # My players per team
        mine = merged[merged['Is_Mine'] == True]
        for _, row in mine.iterrows():
            t = row.get('Team', '')
            if t:
                team_my_players.setdefault(t, []).append(row['name'])

        # Top FAs per team
        fa = merged[merged['Status'] == 'Free Agent'].sort_values('NexusScore', ascending=False)
        for t, group in fa.groupby('Team'):
            top3 = group.head(3)[['name', 'NexusScore']].values.tolist()
            team_top_fa[t] = top3

    # ── Build grid rows ──────────────────────────────────────────────────────
    rows = []
    all_teams = sorted(team_games.keys())

    for team in all_teams:
        games = team_games[team]
        gp      = len(games)
        h_games = sum(1 for g in games.values() if g['home'])
        a_games = gp - h_games
        b2b     = team_b2b.get(team, 0)
        off_nights = sum(
            1 for d_str in games
            if datetime.strptime(d_str, '%Y-%m-%d').weekday() in [0, 2, 4, 6]
        )

        # Opponent avg GA (facing teams that allow more goals = better for scorers)
        opp_ga_list = [
            team_stats.get(g['opp'], {}).get('ga_pg', league_ga_avg)
            for g in games.values()
        ]
        avg_opp_ga = sum(opp_ga_list) / max(len(opp_ga_list), 1)

        ease = _ease_score(gp, h_games, b2b, avg_opp_ga, league_ga_avg)

        row = {
            'Team':   team,
            'GP':     gp,
            'H':      h_games,
            'A':      a_games,
            'B2B':    b2b,
            'Off':    off_nights,
            'Ease':   ease,
        }

        # Day-by-day game cells
        for d_str in day_cols:
            if d_str in games:
                g = games[d_str]
                prefix = 'vs' if g['home'] else '@'
                row[d_str] = f"{prefix} {g['opp']}"
            else:
                row[d_str] = '—'

        # Per-category schedule value
        # Based on: avg opponent GA (vs league avg) → positive = facing weaker defenses
        opp_quality_delta = avg_opp_ga - league_ga_avg

        # Also get avg opponent shots-against for SOG cats
        opp_sa_list = [
            team_stats.get(g['opp'], {}).get('sa_pg', 30.0)
            for g in games.values()
        ]
        avg_opp_sa = sum(opp_sa_list) / max(len(opp_sa_list), 1)
        league_sa_avg = (
            sum(v.get('sa_pg', 30.0) for v in team_stats.values()) / max(len(team_stats), 1)
            if team_stats else 30.0
        )
        opp_sa_delta = avg_opp_sa - league_sa_avg

        for cat in active_cats:
            if cat in ['G', 'A', 'PPP']:
                # Scoring cats: opponent GA delta matters most
                row[f"{cat}V"] = round(opp_quality_delta * gp * 0.15, 2)
            elif cat in ['SOG']:
                # SOG: opponent shots-against (how much they allow shots)
                row[f"{cat}V"] = round(opp_sa_delta * gp * 0.08, 2)
            elif cat in ['+/-']:
                row[f"{cat}V"] = round(opp_quality_delta * gp * 0.10, 2)
            elif cat in ['HIT', 'BLK']:
                # Physical cats less opponent-dependent
                row[f"{cat}V"] = round(opp_quality_delta * gp * 0.05, 2)
            else:
                row[f"{cat}V"] = 0.0

        # My players
        my_players = team_my_players.get(team, [])
        row['My Players'] = ', '.join(my_players[:4]) if my_players else '—'

        # Top FAs
        fa_list = team_top_fa.get(team, [])
        if fa_list:
            row['Top FAs'] = ', '.join(f"{n} ({s:.1f})" for n, s in fa_list[:3])
        else:
            row['Top FAs'] = '—'

        rows.append(row)

    grid_df = pd.DataFrame(rows)
    if not grid_df.empty:
        grid_df = grid_df.sort_values('Ease', ascending=False).reset_index(drop=True)

    return grid_df, week_info, day_cols