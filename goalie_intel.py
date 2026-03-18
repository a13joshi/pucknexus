import requests
import pandas as pd
from datetime import date, datetime


def get_todays_goalies():
    """
    Fetches probable starters from today's NHL schedule.
    Returns a DataFrame with goalie name, team, opponent, home/away, game time, confirmed status.
    """
    try:
        data = requests.get("https://api-web.nhle.com/v1/schedule/now").json()
        today_str = str(date.today())
        games = []

        for day in data.get('gameWeek', []):
            if day['date'] != today_str:
                continue
            for g in day['games']:
                home = g['homeTeam']
                away = g['awayTeam']
                game_time = g.get('startTimeUTC', '')

                for side, opp, is_home in [(home, away, True), (away, home, False)]:
                    goalie = side.get('probableGoalie', {})
                    goalie_name = goalie.get('name', {})
                    if isinstance(goalie_name, dict):
                        goalie_name = goalie_name.get('default', 'TBD')
                    elif not goalie_name:
                        goalie_name = 'TBD'

                    games.append({
                        'Team':       side['abbrev'],
                        'Opponent':   opp['abbrev'],
                        'Home':       is_home,
                        'GameTime':   game_time,
                        'GoalieName': goalie_name,
                        'GoalieId':   goalie.get('id'),
                        'Confirmed':  goalie.get('id') is not None,
                    })

        return pd.DataFrame(games)

    except Exception as e:
        print(f"Goalie fetch error: {e}")
        return pd.DataFrame()


def calculate_sos_score(goalie_df, goalie_season_df):
    """
    Strength of Start (SoS) score: 0-100 composite.

    Weights:
      40% — Personal form (season SV%)
      20% — Home/away advantage
      25% — Opponent offense (goals against per game allowed by opponent)
      15% — Rest (placeholder, set to neutral 50)

    Lower GAA opponents = tougher start = lower SoS.
    Home games get +10 advantage over away.
    """
    if goalie_df.empty or goalie_season_df.empty:
        return goalie_df

    scored = goalie_df.copy()

    # Merge season stats onto today's starters
    g_stats = goalie_season_df[['Player', 'SV%', 'GAA', 'GP', 'W']].copy()
    g_stats['match_key'] = g_stats['Player'].str.lower().str.strip()
    scored['match_key'] = scored['GoalieName'].str.lower().str.strip()
    scored = pd.merge(scored, g_stats, on='match_key', how='left')

    # --- Form score (40%) ---
    sv_col = scored['SV%'].fillna(0.900)
    max_sv = sv_col.max() if sv_col.max() > 0 else 0.920
    min_sv = sv_col.min() if sv_col.min() > 0 else 0.880
    range_sv = max_sv - min_sv if max_sv != min_sv else 0.001
    scored['form_score'] = ((sv_col - min_sv) / range_sv * 100).clip(0, 100)

    # --- Home/away score (20%) ---
    scored['home_score'] = scored['Home'].apply(lambda h: 65 if h else 35)

    # --- Opponent offense score (25%) ---
    # Build a team goals-per-game lookup from season goalie stats
    # Teams that allow more goals = weaker offense against = better start
    # We approximate opponent offense using the avg GAA of goalies facing that team
    # For now use neutral 50 as placeholder — will refine with team stats later
    scored['opp_score'] = 50.0

    # --- Rest score (15%) ---
    scored['rest_score'] = 50.0

    # --- Composite SoS ---
    scored['SoS'] = (
        scored['form_score'] * 0.40 +
        scored['home_score'] * 0.20 +
        scored['opp_score']  * 0.25 +
        scored['rest_score'] * 0.15
    ).round(1)

    # --- Grade ---
    def grade(s):
        if s >= 70: return 'A'
        elif s >= 60: return 'B'
        elif s >= 50: return 'C'
        elif s >= 40: return 'D'
        else: return 'F'

    scored['Grade'] = scored['SoS'].apply(grade)

    return scored.sort_values('SoS', ascending=False).drop(columns=['match_key'], errors='ignore')


def get_goalie_streaming_ranks(goalie_season_df, num_days=7):
    """
    Ranks all goalies by streaming value for the next num_days.
    Combines season SV%, W rate, and upcoming schedule game count.
    Returns top streaming targets.
    """
    if goalie_season_df.empty:
        return pd.DataFrame()

    df = goalie_season_df.copy()
    df = df[df['GP'] >= 5].copy()  # Min 5 GP to be relevant

    # Normalize SV% and W rate
    df['SV%'] = pd.to_numeric(df['SV%'], errors='coerce').fillna(0)
    df['W']   = pd.to_numeric(df['W'],   errors='coerce').fillna(0)
    df['GP']  = pd.to_numeric(df['GP'],  errors='coerce').fillna(1)
    df['GAA'] = pd.to_numeric(df['GAA'], errors='coerce').fillna(3.0)

    df['W_rate'] = df['W'] / df['GP'].clip(lower=1)

    max_sv = df['SV%'].max() or 0.930
    min_sv = df['SV%'].min() or 0.870
    max_wr = df['W_rate'].max() or 1.0

    df['sv_score'] = ((df['SV%'] - min_sv) / (max_sv - min_sv + 0.001) * 100).clip(0, 100)
    df['w_score']  = (df['W_rate'] / max_wr * 100).clip(0, 100)

    # Streaming score: 60% SV%, 40% win rate
    df['StreamScore'] = (df['sv_score'] * 0.60 + df['w_score'] * 0.40).round(1)

    cols = ['Player', 'Team', 'GP', 'W', 'GAA', 'SV%', 'SHO', 'StreamScore']
    available = [c for c in cols if c in df.columns]

    return df[available].sort_values('StreamScore', ascending=False).head(20)
