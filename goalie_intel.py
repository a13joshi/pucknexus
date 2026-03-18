import requests
import pandas as pd
from datetime import date, datetime, timedelta


# External resources to link to in the UI
GOALIE_RESOURCES = [
    {"name": "Daily Faceoff",  "url": "https://www.dailyfaceoff.com/starting-goalies/",  "desc": "Human-confirmed starting goalies"},
    {"name": "Left Wing Lock", "url": "https://leftwinglock.com/starting-goalies/",       "desc": "Early goalie reports + notifications"},
    {"name": "NHL.com",        "url": "https://www.nhl.com/scores",                       "desc": "Official NHL lineup confirmations"},
]


def get_todays_game_ids():
    try:
        data = requests.get("https://api-web.nhle.com/v1/schedule/now", timeout=10).json()
        today_str = str(date.today())
        games = []
        for day in data.get('gameWeek', []):
            if day['date'] != today_str:
                continue
            for g in day['games']:
                games.append({
                    'game_id':    g['id'],
                    'home':       g['homeTeam']['abbrev'],
                    'away':       g['awayTeam']['abbrev'],
                    'game_time':  g.get('startTimeUTC', ''),
                    'game_state': g.get('gameState', 'FUT'),
                })
        return games
    except Exception as e:
        print(f"Game ID fetch error: {e}")
        return []


def get_confirmed_from_boxscore(game_id):
    try:
        bs = requests.get(
            f"https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore",
            timeout=10
        ).json()
        result = {'home': None, 'away': None}
        for side, key in [('homeTeam', 'home'), ('awayTeam', 'away')]:
            team_data = bs.get(side, {})
            goalies = team_data.get('goalies', [])
            if goalies:
                name = goalies[0].get('name', {})
                result[key] = name.get('default', '') if isinstance(name, dict) else name
            if not result[key]:
                pg = team_data.get('probableGoalie', {})
                name = pg.get('name', {})
                result[key] = name.get('default', '') if isinstance(name, dict) else name or None
        return result
    except Exception as e:
        print(f"Boxscore error for {game_id}: {e}")
        return {'home': None, 'away': None}


def get_recent_goalie_starts(season="20252026", days_back=14):
    try:
        since = str(date.today() - timedelta(days=days_back))
        url = "https://api.nhle.com/stats/rest/en/goalie/summary"
        params = {
            "isAggregate": "true",
            "isGame": "false",
            "cayenneExp": f'seasonId={season} and gameTypeId=2 and gameDate >= "{since}"',
            "limit": -1,
        }
        resp = requests.get(url, params=params, timeout=15).json()
        df = pd.DataFrame(resp.get('data', []))
        if df.empty:
            return pd.DataFrame()
        rename = {'goalieFullName': 'Player', 'teamAbbrevs': 'Team', 'gamesPlayed': 'recent_GP'}
        return df[[c for c in rename if c in df.columns]].rename(columns=rename)
    except Exception as e:
        print(f"Recent starts error: {e}")
        return pd.DataFrame()


def project_starters_from_rotation(todays_games, season_goalie_df):
    if season_goalie_df.empty or not todays_games:
        return pd.DataFrame()

    g_df = season_goalie_df[season_goalie_df['GP'] >= 5].copy()

    # Primary/backup per team by GP
    team_starters = {}
    for team, group in g_df.groupby('Team'):
        starters = group.sort_values('GP', ascending=False)
        team_starters[team] = {
            'starter': starters.iloc[0]['Player'],
            'backup':  starters.iloc[1]['Player'] if len(starters) >= 2 else 'Unknown',
        }

    # Check B2B
    yesterday = str(date.today() - timedelta(days=1))
    played_yesterday = set()
    try:
        ys = requests.get(f"https://api-web.nhle.com/v1/schedule/{yesterday}", timeout=10).json()
        for day in ys.get('gameWeek', []):
            if day['date'] == yesterday:
                for g in day['games']:
                    played_yesterday.add(g['homeTeam']['abbrev'])
                    played_yesterday.add(g['awayTeam']['abbrev'])
    except Exception:
        pass

    rows = []
    for game in todays_games:
        for team, opp, is_home in [
            (game['home'], game['away'], True),
            (game['away'], game['home'], False)
        ]:
            info = team_starters.get(team, {})
            is_b2b = team in played_yesterday
            projected = info.get('backup', 'Unknown') if is_b2b else info.get('starter', 'Unknown')
            rows.append({
                'Team':      team,
                'Opponent':  opp,
                'Home':      is_home,
                'GameTime':  game.get('game_time', ''),
                'Projected': projected,
                'B2B':       is_b2b,
                'Note':      '⚠️ B2B — backup likely' if is_b2b else '📊 Rotation model',
            })
    return pd.DataFrame(rows)


def get_todays_goalies(season_goalie_df=None):
    """
    Master function combining:
    1. NHL API probable goalie (schedule endpoint)
    2. Boxscore confirmed (if game started)
    3. Rotation model projection (TBD fallback)
    """
    try:
        todays_games = get_todays_game_ids()
        if not todays_games:
            return pd.DataFrame()

        today_str = str(date.today())

        # Probable goalies from schedule
        schedule_data = requests.get("https://api-web.nhle.com/v1/schedule/now", timeout=10).json()
        probable = {}
        for day in schedule_data.get('gameWeek', []):
            if day['date'] != today_str:
                continue
            for g in day['games']:
                for side in [g['homeTeam'], g['awayTeam']]:
                    pg = side.get('probableGoalie', {})
                    name = pg.get('name', {})
                    name = name.get('default', '') if isinstance(name, dict) else name
                    if name:
                        probable[side['abbrev']] = {'name': name, 'id': pg.get('id')}

        # Confirmed from boxscore (in-progress/finished games)
        confirmed = {}
        for game in todays_games:
            if game.get('game_state') not in ['FUT', 'PRE']:
                bs = get_confirmed_from_boxscore(game['game_id'])
                if bs['home']: confirmed[game['home']] = bs['home']
                if bs['away']: confirmed[game['away']] = bs['away']

        # Build rows
        rows = []
        for game in todays_games:
            for team, opp, is_home in [
                (game['home'], game['away'], True),
                (game['away'], game['home'], False)
            ]:
                if team in confirmed:
                    goalie_name, status = confirmed[team], 'Confirmed'
                elif team in probable:
                    goalie_name, status = probable[team]['name'], 'Probable'
                else:
                    goalie_name, status = 'TBD', 'TBD'

                rows.append({
                    'Team':       team,
                    'Opponent':   opp,
                    'Home':       is_home,
                    'GameTime':   game.get('game_time', ''),
                    'GoalieName': goalie_name,
                    'Status':     status,
                    'Confirmed':  status == 'Confirmed',
                    'Note':       '',
                })

        df = pd.DataFrame(rows)

        # Fill TBD with rotation model
        if season_goalie_df is not None and not season_goalie_df.empty:
            tbd_teams = set(df[df['Status'] == 'TBD']['Team'].tolist())
            tbd_games = [g for g in todays_games
                         if g['home'] in tbd_teams or g['away'] in tbd_teams]
            if tbd_games:
                proj_df = project_starters_from_rotation(tbd_games, season_goalie_df)
                if not proj_df.empty:
                    for _, prow in proj_df.iterrows():
                        mask = (df['Team'] == prow['Team']) & (df['Status'] == 'TBD')
                        if mask.any():
                            df.loc[mask, 'GoalieName'] = prow['Projected']
                            df.loc[mask, 'Status']     = 'Projected'
                            df.loc[mask, 'Note']       = prow.get('Note', '📊 Rotation model')

        return df

    except Exception as e:
        print(f"get_todays_goalies error: {e}")
        return pd.DataFrame()


def calculate_sos_score(goalie_df, goalie_season_df):
    if goalie_df.empty or goalie_season_df.empty:
        return goalie_df

    scored = goalie_df.copy()
    g_stats = goalie_season_df[['Player', 'SV%', 'GAA', 'GP', 'W']].copy()
    g_stats['match_key'] = g_stats['Player'].str.lower().str.strip()
    scored['match_key']  = scored['GoalieName'].str.lower().str.strip()
    scored = pd.merge(scored, g_stats, on='match_key', how='left')

    sv_col  = scored['SV%'].fillna(0.900)
    max_sv  = sv_col.max() if sv_col.max() > 0 else 0.920
    min_sv  = sv_col.min() if sv_col.min() > 0 else 0.880
    rng     = max_sv - min_sv if max_sv != min_sv else 0.001

    scored['form_score'] = ((sv_col - min_sv) / rng * 100).clip(0, 100)
    scored['home_score'] = scored['Home'].apply(lambda h: 65 if h else 35)

    scored['SoS'] = (
        scored['form_score'] * 0.40 +
        scored['home_score'] * 0.20 +
        50.0 * 0.25 +  # opponent placeholder
        50.0 * 0.15    # rest placeholder
    ).round(1)

    scored['Grade'] = scored['SoS'].apply(
        lambda s: 'A' if s >= 70 else 'B' if s >= 60 else 'C' if s >= 50 else 'D' if s >= 40 else 'F'
    )

    return scored.sort_values('SoS', ascending=False).drop(columns=['match_key'], errors='ignore')


def get_goalie_streaming_ranks(goalie_season_df):
    if goalie_season_df.empty:
        return pd.DataFrame()

    df = goalie_season_df[goalie_season_df['GP'] >= 5].copy()
    for col in ['SV%', 'W', 'GP', 'GAA']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    df['W_rate']  = df['W'] / df['GP'].clip(lower=1)
    max_sv = df['SV%'].max() or 0.930
    min_sv = df['SV%'].min() or 0.870
    max_wr = df['W_rate'].max() or 1.0

    df['sv_score']    = ((df['SV%'] - min_sv) / (max_sv - min_sv + 0.001) * 100).clip(0, 100)
    df['w_score']     = (df['W_rate'] / max_wr * 100).clip(0, 100)
    df['StreamScore'] = (df['sv_score'] * 0.60 + df['w_score'] * 0.40).round(1)

    cols = ['Player', 'Team', 'GP', 'W', 'GAA', 'SV%', 'SHO', 'StreamScore']
    return df[[c for c in cols if c in df.columns]].sort_values('StreamScore', ascending=False).head(20)