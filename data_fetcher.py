import requests
import pandas as pd
from datetime import datetime, timedelta, date
from supabase_config import supabase  # Added for Phase 2

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
    # --- PHASE 2: SUPABASE CACHE CHECK ---
    # Only use cache for 'Full Season' (where start_date/end_date are None) to keep it simple
    if start_date is None and end_date is None:
        try:
            # Check the timestamp of the last update
            existing = supabase.table("skater_stats").select("updated_at").limit(1).execute()
            
            if existing.data:
                last_update = datetime.fromisoformat(existing.data[0]['updated_at'].replace('Z', '+00:00'))
                # If data is less than 24 hours old, return from DB
                if datetime.now(last_update.tzinfo) - last_update < timedelta(hours=24):
                    print("📦 PuckNexus Cache Hit: Loading from Supabase...")
                    full_db = supabase.table("skater_stats").select("*").execute()
                    db_df = pd.DataFrame(full_db.data)
                    
                    # Map SQL column names back to PuckNexus dataframe names
                    return db_df.rename(columns={
                        'player_id': 'playerId', 'player_name': 'Player', 
                        'team_abbrev': 'Team', 'position_code': 'Pos',
                        'gp': 'GP', 'goals': 'G', 'assists': 'A', 'points': 'PTS',
                        'plus_minus': '+/-', 'pim': 'PIM', 'ppp': 'PPP', 
                        'shots': 'SOG', 'hits': 'HIT', 'blocks': 'BLK'
                    })
        except Exception as e:
            print(f"⚠️ Cache check failed or table empty: {e}")

    # --- FALLBACK: ORIGINAL API FETCH LOGIC ---
    print("🌐 Cache stale or custom timeframe: Fetching from NHL API...")
    summary_url = "https://api.nhle.com/stats/rest/en/skater/summary"
    realtime_url = "https://api.nhle.com/stats/rest/en/skater/realtime"

    cayenne_exp = f"seasonId={season} and gameTypeId=2"
    if start_date:
        cayenne_exp += f" and gameDate >= \"{start_date}\""
    if end_date:
        cayenne_exp += f" and gameDate <= \"{end_date}\""

    params = {
        "isAggregate": "false", 
        "isGame": "false", 
        "sort": "[{\"property\":\"points\",\"direction\":\"DESC\"}]", 
        "cayenneExp": cayenne_exp
    }

    try:
        # 1. Fetch ALL Summary Data
        df_s = _fetch_all(summary_url, params.copy())
        if df_s.empty: return pd.DataFrame()

        # 2. Fetch ALL Realtime Data
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

        # 4. Cleanup & Format
        for c in ['HIT', 'BLK']: 
            if c not in combined.columns: combined[c] = 0
            combined[c] = pd.to_numeric(combined[c], errors='coerce').fillna(0).astype(int)

        rename_map = {
            'skaterFullName': 'Player', 'teamAbbrevs': 'Team', 'positionCode': 'Pos',
            'gamesPlayed': 'GP', 'goals': 'G', 'assists': 'A', 'points': 'PTS',
            'plusMinus': '+/-', 'penaltyMinutes': 'PIM', 'ppPoints': 'PPP', 'shots': 'SOG'
        }
        
        final_cols = ['playerId'] + [c for c in rename_map.keys() if c in combined.columns] + ['HIT', 'BLK']
        final_df = combined[final_cols].rename(columns=rename_map)

# --- PHASE 2: UPDATE SUPABASE CACHE ---
        if not final_df.empty and start_date is None:
            # Prepare dictionary for SQL
            upload_df = final_df.rename(columns={
                'playerId': 'player_id', 'Player': 'player_name', 
                'Team': 'team_abbrev', 'Pos': 'position_code',
                'GP': 'gp', 'G': 'goals', 'A': 'assists', 'PTS': 'points',
                '+/-': 'plus_minus', 'PIM': 'pim', 'PPP': 'ppp', 
                'SOG': 'shots', 'HIT': 'hits', 'BLK': 'blocks'
            })

            # 🔥 FIX: Remove duplicate player IDs before sending to Supabase
            upload_df = upload_df.drop_duplicates(subset=['player_id'])
            
            upload_data = upload_df.to_dict(orient='records')
            
            # Upsert into Supabase
            supabase.table("skater_stats").upsert(upload_data).execute()
            print("💾 Supabase Cache Updated.")
            
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
        
        available_cols = ['playerId'] + [c for c in rename_map.keys() if c in final_df.columns]
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