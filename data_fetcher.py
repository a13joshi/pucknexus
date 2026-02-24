import requests
import pandas as pd
from datetime import datetime, timedelta, date

# --- HELPER: PAGINATION ENGINE ---
def _fetch_all(url, params, limit=100):
    """
    Loops through the API in chunks (pages) to ensure we get EVERY player,
    bypassing server-side limits that cut off data.
    """
    all_data = []
    current_start = 0
    
    # Force a safe limit chunk size (API often breaks if requested > 100 at once for aggregates)
    params['limit'] = limit 
    
    while True:
        params['start'] = current_start
        try:
            resp = requests.get(url, params=params).json()
            data = resp.get('data', [])
            
            if not data:
                break
                
            all_data.extend(data)
            
            # If we got fewer items than the limit, we've reached the end
            if len(data) < limit:
                break
                
            current_start += limit
            
        except Exception as e:
            print(f"❌ Error during pagination at index {current_start}: {e}")
            break
            
    return pd.DataFrame(all_data)

# --- SKATERS ---
def get_nhl_skater_stats(season="20252026", start_date=None, end_date=None):
    summary_url = "https://api.nhle.com/stats/rest/en/skater/summary"
    realtime_url = "https://api.nhle.com/stats/rest/en/skater/realtime"

    cayenne_exp = f"seasonId={season} and gameTypeId=2"
    if start_date:
        cayenne_exp += f" and gameDate >= \"{start_date}\""
    if end_date:
        cayenne_exp += f" and gameDate <= \"{end_date}\""

    # Base Params
    params = {
        "isAggregate": "false", 
        "isGame": "false", 
        "sort": "[{\"property\":\"points\",\"direction\":\"DESC\"}]", 
        "cayenneExp": cayenne_exp
    }

    try:
        # 1. Fetch ALL Summary Data (Looping)
        df_s = _fetch_all(summary_url, params.copy())
        if df_s.empty: return pd.DataFrame()

        # 2. Fetch ALL Realtime Data (Looping)
        rt_params = params.copy()
        if "sort" in rt_params: del rt_params["sort"]
        if start_date: rt_params["isAggregate"] = "true"
        
        df_r = _fetch_all(realtime_url, rt_params)

        # 3. Merge Logic
        if not df_r.empty:
            df_s['playerId'] = df_s['playerId'].astype(int)
            df_r['playerId'] = df_r['playerId'].astype(int)

            mapper = {'hits': 'HIT', 'totalHits': 'HIT', 'blockedShots': 'BLK', 'totalBlockedShots': 'BLK'}
            found = {k: v for k, v in mapper.items() if k in df_r.columns}
            
            if found:
                df_r = df_r[['playerId'] + list(found.keys())].rename(columns=mapper)
                combined = pd.merge(df_s, df_r, on='playerId', how='left')
            else:
                combined = df_s.copy()
        else:
            combined = df_s.copy()

        # 4. Fill Missing & Clean Up
        for c in ['HIT', 'BLK']: 
            if c not in combined.columns: combined[c] = 0
            combined[c] = pd.to_numeric(combined[c], errors='coerce').fillna(0).astype(int)

        rename_map = {
            'skaterFullName': 'Player', 'teamAbbrevs': 'Team', 'positionCode': 'Pos',
            'gamesPlayed': 'GP', 'goals': 'G', 'assists': 'A', 'plusMinus': '+/-', 
            'penaltyMinutes': 'PIM', 'ppPoints': 'PPP', 'shots': 'SOG'
        }
        
        # 🟢 FIX: Explicitly add 'playerId' to the list so it doesn't get dropped
        final_cols = ['playerId'] + [c for c in rename_map.keys() if c in combined.columns] + ['HIT', 'BLK']
        
        final_df = combined[final_cols].rename(columns=rename_map)
            
        return final_df

    except Exception as e:
        print(f"❌ Error fetching skaters: {e}")
        return pd.DataFrame()
    

# --- GOALIES ---
def get_nhl_goalie_stats(season="20252026", start_date=None, end_date=None):
    url = "https://api.nhle.com/stats/rest/en/goalie/summary"
    
    cayenne_exp = f"seasonId={season} and gameTypeId=2"
    if start_date:
        cayenne_exp += f" and gameDate >= \"{start_date}\""
    if end_date:
        cayenne_exp += f" and gameDate <= \"{end_date}\""

    params = {
        "isAggregate": "false", "isGame": "false",
        "sort": "[{\"property\":\"wins\",\"direction\":\"DESC\"}]",
        "cayenneExp": cayenne_exp
    }

    try:
        final_df = _fetch_all(url, params)
        if final_df.empty: return pd.DataFrame()

        rename_map = {
            'goalieFullName': 'Player', 'teamAbbrevs': 'Team',
            'gamesPlayed': 'GP', 'wins': 'W', 'goalsAgainstAverage': 'GAA',
            'savePct': 'SV%', 'shutouts': 'SHO'
        }
        
        # 🟢 FIX: Keep 'playerId' here too for future-proofing
        available_cols = ['playerId'] + [c for c in rename_map.keys() if c in final_df.columns]
        
        # Use intersection to avoid KeyErrors if playerId is missing from API (rare)
        available_cols = [c for c in available_cols if c in final_df.columns]
        
        final_df = final_df[available_cols].rename(columns=rename_map)
        
        goalie_nums = ['GP', 'W', 'GAA', 'SV%', 'SHO']
        for col in goalie_nums:
            if col in final_df.columns:
                final_df[col] = pd.to_numeric(final_df[col], errors='coerce').fillna(0).astype(float)

        return final_df

    except Exception as e:
        print(f"❌ Error fetching goalies: {e}")
        return pd.DataFrame()

# --- UTILS ---
def get_fantasy_weeks(season_start=date(2025, 10, 7), num_weeks=26):
    weeks = []
    curr = season_start
    for i in range(1, num_weeks + 1):
        end = curr + timedelta(days=6)
        weeks.append({'label': f"Week {i}: {curr.strftime('%b %d')} - {end.strftime('%b %d')}", 'start': curr, 'end': end})
        curr = end + timedelta(days=1)
    return weeks

def get_nhl_schedule(start_date=None):
    url = f"https://api-web.nhle.com/v1/schedule/{start_date}" if start_date else "https://api-web.nhle.com/v1/schedule/now"
    try:
        data = requests.get(url).json()
        schedule = {}
        for day in data.get('gameWeek', []):
            date_str = day['date']
            games = {}
            for g in day['games']:
                h, a = g['homeTeam']['abbrev'], g['awayTeam']['abbrev']
                games[h] = f"vs {a}"; games[a] = f"@ {h}"
            schedule[date_str] = games
        return schedule
    except: return {}