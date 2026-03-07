import requests
import pandas as pd
from datetime import datetime, timedelta, date
from supabase_config import supabase  # Added for Phase 2

# --- HELPER: PAGINATION ENGINE ---
def _fetch_all(url, params, limit=100):
    """
    Loops through the API in chunks (pages) to ensure we get EVERY player.
    Includes smart-routing for aggregates and emergency loop-breakers.
    """
    # 1. SMART ROUTING: The NHL API breaks pagination on custom date ranges. 
    # If we are aggregating, we must pull everyone in one giant chunk (limit=-1).
    if params.get("isAggregate") == "true":
        params['limit'] = -1
        try:
            resp = requests.get(url, params=params).json()
            return pd.DataFrame(resp.get('data', []))
        except Exception as e:
            print(f"❌ Error fetching aggregate data: {e}")
            return pd.DataFrame()

    # 2. STANDARD PAGINATION: For normal Full Season pulls
    all_data = []
    current_start = 0
    params['limit'] = limit 
    
    # Track the first player of each page to detect infinite API loops
    seen_signatures = set()
    
    while True:
        params['start'] = current_start
        try:
            resp = requests.get(url, params=params).json()
            data = resp.get('data', [])
            
            if not data:
                break
                
            # 🛑 INF-LOOP BREAKER: If the API ignores the 'start' parameter and 
            # feeds us the exact same page we just looked at, break the loop!
            page_sig = str(data[0].get('playerId', current_start))
            if page_sig in seen_signatures:
                print("⚠️ NHL API ignored pagination offset. Breaking loop to prevent crash.")
                break
            seen_signatures.add(page_sig)
                
            all_data.extend(data)
            
            # If we got fewer items than the limit, we've reached the end
            if len(data) < limit:
                break
                
            current_start += limit
            
            # Emergency fallback (there are only ~900 NHL players)
            if current_start > 5000:
                break
                
        except Exception as e:
            print(f"❌ Error during pagination at index {current_start}: {e}")
            break
            
    return pd.DataFrame(all_data)

# --- SKATERS ---
def get_nhl_skater_stats(season="20252026", start_date=None, end_date=None):
    # Determine if this is a standard full-season pull to safely use the cache
    is_full_season = start_date is None and (end_date is None or end_date == str(date.today()))
    
    # --- PHASE 2: SUPABASE CACHE CHECK ---
    if is_full_season:
        try:
            existing = supabase.table("skater_stats").select("updated_at").limit(1).execute()
            
            if existing.data:
                last_update = datetime.fromisoformat(existing.data[0]['updated_at'].replace('Z', '+00:00'))
                if datetime.now(last_update.tzinfo) - last_update < timedelta(hours=24):
                    print("📦 PuckNexus Cache Hit: Loading from Supabase...")
                    full_db = supabase.table("skater_stats").select("*").execute()
                    db_df = pd.DataFrame(full_db.data)
                    
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
    if start_date: cayenne_exp += f" and gameDate >= \"{start_date}\""
    if end_date: cayenne_exp += f" and gameDate <= \"{end_date}\""

    params = {
        "isAggregate": "true" if (start_date or end_date) else "false", 
        "isGame": "false", 
        "sort": "[{\"property\":\"points\",\"direction\":\"DESC\"}]", 
        "cayenneExp": cayenne_exp
    }

    try:
        df_s = _fetch_all(summary_url, params.copy())
        if df_s.empty: return pd.DataFrame()

        # FIX 1: Force Realtime aggregation for ANY custom date range
        rt_params = params.copy()
        if "sort" in rt_params: del rt_params["sort"]
        if start_date or end_date: rt_params["isAggregate"] = "true" 
        
        df_r = _fetch_all(realtime_url, rt_params)

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

        # FIX 2: Only update Supabase if it's a true full season pull
        if not final_df.empty and is_full_season:
            upload_df = final_df.rename(columns={
                'playerId': 'player_id', 'Player': 'player_name', 
                'Team': 'team_abbrev', 'Pos': 'position_code',
                'GP': 'gp', 'G': 'goals', 'A': 'assists', 'PTS': 'points',
                '+/-': 'plus_minus', 'PIM': 'pim', 'PPP': 'ppp', 
                'SOG': 'shots', 'HIT': 'hits', 'BLK': 'blocks'
            }).drop_duplicates(subset=['player_id'])
            
            upload_data = upload_df.to_dict(orient='records')
            supabase.table("skater_stats").upsert(upload_data).execute()
            print("💾 Supabase Skater Cache Updated.")
            
        return final_df

    except Exception as e:
        print(f"❌ Error fetching skaters: {e}")
        return pd.DataFrame()
    

# --- GOALIES ---
def get_nhl_goalie_stats(season="20252026", start_date=None, end_date=None):
    is_full_season = start_date is None and (end_date is None or end_date == str(date.today()))
    
    # --- SUPABASE CACHE CHECK ---
    if is_full_season:
        try:
            existing = supabase.table("goalie_stats").select("updated_at").limit(1).execute()
            
            if existing.data:
                last_update = datetime.fromisoformat(existing.data[0]['updated_at'].replace('Z', '+00:00'))
                if datetime.now(last_update.tzinfo) - last_update < timedelta(hours=24):
                    print("📦 PuckNexus Cache Hit: Loading Goalies from Supabase...")
                    full_db = supabase.table("goalie_stats").select("*").execute()
                    db_df = pd.DataFrame(full_db.data)
                    
                    return db_df.rename(columns={
                        'player_id': 'playerId', 'player_name': 'Player', 
                        'team_abbrev': 'Team', 'gp': 'GP', 'w': 'W', 
                        'gaa': 'GAA', 'sv_pct': 'SV%', 'sho': 'SHO'
                    })
        except Exception as e:
            print(f"⚠️ Goalie cache check failed: {e}")

    # --- FALLBACK: ORIGINAL API FETCH LOGIC ---
    print("🌐 Fetching Goalies from NHL API...")
    url = "https://api.nhle.com/stats/rest/en/goalie/summary"
    
    cayenne_exp = f"seasonId={season} and gameTypeId=2"
    if start_date: cayenne_exp += f" and gameDate >= \"{start_date}\""
    if end_date: cayenne_exp += f" and gameDate <= \"{end_date}\""

    params = {
        "isAggregate": "true" if (start_date or end_date) else "false", 
        "isGame": "false",
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
        final_df = final_df[available_cols].rename(columns=rename_map)
        
        int_cols = ['GP', 'W', 'SHO']
        for col in int_cols:
            if col in final_df.columns:
                final_df[col] = pd.to_numeric(final_df[col], errors='coerce').fillna(0).astype(int)
                
        float_cols = ['GAA', 'SV%']
        for col in float_cols:
            if col in final_df.columns:
                final_df[col] = pd.to_numeric(final_df[col], errors='coerce').fillna(0.0).astype(float)

        # FIX 2: Only update Supabase if it's a true full season pull
        if not final_df.empty and is_full_season:
            upload_df = final_df.rename(columns={
                'playerId': 'player_id', 'Player': 'player_name', 
                'Team': 'team_abbrev', 'GP': 'gp', 'W': 'w', 
                'GAA': 'gaa', 'SV%': 'sv_pct', 'SHO': 'sho'
            }).drop_duplicates(subset=['player_id'])
            
            upload_data = upload_df.to_dict(orient='records')
            supabase.table("goalie_stats").upsert(upload_data).execute()
            print("💾 Supabase Goalie Cache Updated.")

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