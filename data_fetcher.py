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

    is_full_season = start_date is None and end_date is None
    
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
                        'shots': 'SOG', 'hits': 'HIT', 'blocks': 'BLK',
                        'shp': 'SHP', 'gwg': 'GWG', 'toi': 'TOI'
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

        # Fetch TOI from timeonice endpoint
        bio_url = "https://api.nhle.com/stats/rest/en/skater/timeonice"
        bio_params = {
            "isAggregate": "false",
            "isGame": "false",
            "cayenneExp": f"seasonId={season} and gameTypeId=2"
        }
        if start_date: bio_params["cayenneExp"] += f" and gameDate >= \"{start_date}\""
        if end_date: bio_params["cayenneExp"] += f" and gameDate <= \"{end_date}\""
        if start_date or end_date: bio_params["isAggregate"] = "true"
        df_bio = _fetch_all(bio_url, bio_params)
        if not df_bio.empty and 'timeOnIcePerGame' in df_bio.columns:
            df_bio['playerId'] = df_bio['playerId'].astype(int)
            df_bio = df_bio[['playerId', 'timeOnIcePerGame']].rename(columns={'timeOnIcePerGame': 'TOI'})
            combined = pd.merge(combined, df_bio, on='playerId', how='left', suffixes=('', '_toi'))

        for c in ['HIT', 'BLK']: 
            if c not in combined.columns: combined[c] = 0
            combined[c] = pd.to_numeric(combined[c], errors='coerce').fillna(0).astype(int)

        rename_map = {
            'skaterFullName': 'Player', 'teamAbbrevs': 'Team', 'positionCode': 'Pos',
            'gamesPlayed': 'GP', 'goals': 'G', 'assists': 'A', 'points': 'PTS',
            'plusMinus': '+/-', 'penaltyMinutes': 'PIM', 'ppPoints': 'PPP', 'shots': 'SOG',
            'shPoints': 'SHP', 'gameWinningGoals': 'GWG'
        }

        final_cols = ['playerId'] + [c for c in rename_map.keys() if c in combined.columns] + ['HIT', 'BLK']
        final_df = combined[final_cols].rename(columns=rename_map)

        # Add TOI after rename
        if 'TOI' in combined.columns:
            final_df['TOI'] = combined['TOI'].values

        # Only update Supabase if it's a true full season pull
        if not final_df.empty and is_full_season:
            try:
                upload_df = final_df.rename(columns={
                    'playerId': 'player_id', 'Player': 'player_name', 
                    'Team': 'team_abbrev', 'Pos': 'position_code',
                    'GP': 'gp', 'G': 'goals', 'A': 'assists', 'PTS': 'points',
                    '+/-': 'plus_minus', 'PIM': 'pim', 'PPP': 'ppp', 
                    'SOG': 'shots', 'HIT': 'hits', 'BLK': 'blocks',
                    'SHP': 'shp', 'GWG': 'gwg', 'TOI': 'toi'
                }).drop_duplicates(subset=['player_id'])
                upload_df = upload_df.fillna(0)
                upload_data = upload_df.to_dict(orient='records')
                supabase.table("skater_stats").upsert(upload_data).execute()
                print("💾 Supabase Skater Cache Updated.")
            except Exception as e:
                print(f"⚠️ Supabase upsert failed (schema cache?): {e}")
            
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
def get_fantasy_weeks(season_start=date(2025, 10, 6), num_weeks=26):
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

def get_blended_projections(season="20252026", recent_days=21, recent_weight=0.65, season_end_date=None):
    """
    Projects remaining stats for all skaters AND goalies for the rest of the fantasy season.

    For each player:
      - Blended per-game rate = (65% × last 21 days pace) + (35% × full season pace)
      - GP = remaining NHL games from today to season_end_date
      - Projected stat = blended_pg_rate × remaining_GP

    Args:
        season:           NHL season string e.g. "20252026"
        recent_days:      Days back for recent window (default 21)
        recent_weight:    Weight for recent pace (default 0.65)
        season_end_date:  Last date to count games (date object or str). 
                          Defaults to end of NHL regular season (Apr 17, 2026).

    Returns:
        Dict with keys 'skaters' and 'goalies', each a DataFrame with:
          Player, Team, Pos, Rem_GP, and projected stat totals
    """
    from datetime import date as date_type

    season_weight = 1.0 - recent_weight
    recent_start  = str(date.today() - timedelta(days=recent_days))
    today_str     = str(date.today())

    # Default end date: NHL regular season end
    if season_end_date is None:
        season_end_date = date_type(2026, 4, 17)
    elif isinstance(season_end_date, str):
        season_end_date = date_type.fromisoformat(season_end_date)

    end_str = str(season_end_date)

    print(f"🔀 Blended ROS projections to {end_str} ({int(recent_weight*100)}% last {recent_days}d / {int(season_weight*100)}% season)...")

    # ── 1. Build remaining schedule game count per team ───────────────────────
    rem_games_by_team = {}
    try:
        # Use existing multi-week schedule function — covers all remaining weeks efficiently
        week_data, future_weeks = get_multi_week_schedule(num_weeks=12)
        for week in future_weeks:
            for team, counts in week_data.get(week['label'], {}).items():
                # Only count games up to end_str
                if str(week['start']) <= end_str:
                    gp = counts.get('GP', 0)
                    rem_games_by_team[team] = rem_games_by_team.get(team, 0) + gp
    except Exception as e:
        print(f"⚠️ Schedule fetch error: {e}")

    # ── 2. Skater projections ─────────────────────────────────────────────────
    df_season = get_nhl_skater_stats(season)
    df_recent = get_nhl_skater_stats(season, start_date=recent_start)

    skater_stat_cols = [c for c in ['G', 'A', '+/-', 'PIM', 'PPP', 'SOG', 'HIT', 'BLK', 'SHP', 'GWG'] if c in df_season.columns]
    skater_result    = pd.DataFrame()

    if not df_season.empty:
        df_s = df_season.copy()
        df_s['GP'] = pd.to_numeric(df_s['GP'], errors='coerce').fillna(1).clip(lower=1)
        for c in skater_stat_cols:
            df_s[c] = pd.to_numeric(df_s[c], errors='coerce').fillna(0)
            df_s[f"{c}_s_pg"] = df_s[c] / df_s['GP']

        if not df_recent.empty:
            df_r = df_recent.copy()
            df_r['GP'] = pd.to_numeric(df_r['GP'], errors='coerce').fillna(1).clip(lower=1)
            for c in skater_stat_cols:
                df_r[c] = pd.to_numeric(df_r[c], errors='coerce').fillna(0)
                df_r[f"{c}_r_pg"] = df_r[c] / df_r['GP']
            merged = pd.merge(df_s, df_r[['Player'] + [f"{c}_r_pg" for c in skater_stat_cols]], on='Player', how='left')
        else:
            merged = df_s.copy()
            for c in skater_stat_cols:
                merged[f"{c}_r_pg"] = merged[f"{c}_s_pg"]

        # Blended rate + remaining games
        merged['Rem_GP'] = merged['Team'].map(rem_games_by_team).fillna(0).astype(int)
        out_rows = []
        for c in skater_stat_cols:
            r_pg = merged.get(f"{c}_r_pg", merged[f"{c}_s_pg"]).fillna(merged[f"{c}_s_pg"])
            merged[f"{c}_blended"] = (recent_weight * r_pg + season_weight * merged[f"{c}_s_pg"])
            merged[c] = (merged[f"{c}_blended"] * merged['Rem_GP']).round(1)

        keep = ['Player', 'Team', 'Pos', 'Rem_GP'] + skater_stat_cols
        keep = [c for c in keep if c in merged.columns]
        skater_result = merged[keep].rename(columns={'Rem_GP': 'GP'})
        skater_result = skater_result[skater_result['GP'] > 0]

    # ── 3. Goalie projections ─────────────────────────────────────────────────
    g_season = get_nhl_goalie_stats(season)
    g_recent = get_nhl_goalie_stats(season, start_date=recent_start)
    goalie_stat_cols = [c for c in ['W', 'GAA', 'SV%', 'SHO'] if c in g_season.columns]
    goalie_result    = pd.DataFrame()

    if not g_season.empty:
        dg_s = g_season.copy()
        dg_s['GP'] = pd.to_numeric(dg_s['GP'], errors='coerce').fillna(1).clip(lower=1)
        for c in goalie_stat_cols:
            dg_s[c] = pd.to_numeric(dg_s[c], errors='coerce').fillna(0)
            dg_s[f"{c}_s_pg"] = dg_s[c] / dg_s['GP']

        if not g_recent.empty:
            dg_r = g_recent.copy()
            dg_r['GP'] = pd.to_numeric(dg_r['GP'], errors='coerce').fillna(1).clip(lower=1)
            for c in goalie_stat_cols:
                dg_r[c] = pd.to_numeric(dg_r[c], errors='coerce').fillna(0)
                dg_r[f"{c}_r_pg"] = dg_r[c] / dg_r['GP']
            gmerged = pd.merge(dg_s, dg_r[['Player'] + [f"{c}_r_pg" for c in goalie_stat_cols]], on='Player', how='left')
        else:
            gmerged = dg_s.copy()
            for c in goalie_stat_cols:
                gmerged[f"{c}_r_pg"] = gmerged[f"{c}_s_pg"]

        gmerged['Rem_GP'] = gmerged['Team'].map(rem_games_by_team).fillna(0).astype(int)
        for c in goalie_stat_cols:
            r_pg = gmerged.get(f"{c}_r_pg", gmerged[f"{c}_s_pg"]).fillna(gmerged[f"{c}_s_pg"])
            gmerged[f"{c}_blended"] = (recent_weight * r_pg + season_weight * gmerged[f"{c}_s_pg"])
            if c == 'GAA':
                # GAA is a rate — don't multiply by GP
                gmerged[c] = gmerged[f"{c}_blended"].round(2)
            elif c == 'SV%':
                gmerged[c] = gmerged[f"{c}_blended"].round(3)
            else:
                gmerged[c] = (gmerged[f"{c}_blended"] * gmerged['Rem_GP']).round(1)

        gkeep = ['Player', 'Team', 'Rem_GP'] + goalie_stat_cols
        gkeep = [c for c in gkeep if c in gmerged.columns]
        goalie_result = gmerged[gkeep].rename(columns={'Rem_GP': 'GP'})
        goalie_result = goalie_result[goalie_result['GP'] > 0]
        goalie_result['Pos'] = 'G'

    return {'skaters': skater_result, 'goalies': goalie_result, 'end_date': end_str}


def get_multi_week_schedule(num_weeks=8):
    """
    Returns game counts per team for the next num_weeks fantasy weeks.
    Each week entry: { team: { 'GP': int, 'OFF': int (off-night games) } }
    Off-nights = Mon, Wed, Fri, Sun (days with fewer games = more value)
    """
    weeks = get_fantasy_weeks()
    today = date.today()
    future_weeks = [w for w in weeks if w['end'] >= today][:num_weeks]
    week_data = {}

    for week in future_weeks:
        label     = week['label']
        start_str = str(week['start'])
        end_str   = str(week['end'])
        sched     = get_nhl_schedule(start_str)
        week_data[label] = {}

        for d, games in sched.items():
            if start_str <= d <= end_str:
                dt     = datetime.strptime(d, '%Y-%m-%d')
                is_off = dt.weekday() in [0, 2, 4, 6]  # Mon, Wed, Fri, Sun
                for team in games.keys():
                    if team not in week_data[label]:
                        week_data[label][team] = {'GP': 0, 'OFF': 0}
                    week_data[label][team]['GP'] += 1
                    if is_off:
                        week_data[label][team]['OFF'] += 1

    return week_data, future_weeks