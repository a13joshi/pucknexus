import yahoo_fantasy_api as yfa
from yahoo_oauth import OAuth2
import pandas as pd
import json
from supabase_config import supabase  # Added for Phase 2

def connect_to_yahoo():
    # 1. Fetch tokens from Supabase instead of local file
    try:
        response = supabase.table("auth_vault").select("*").eq("id", "yahoo_token").execute()
        if not response.data:
            print("❌ No tokens found in Supabase. Run migrate_auth.py first.")
            return None
        
        db_data = response.data[0]
        
        # 2. Reconstruct the structure for the Yahoo OAuth library
        # We pass the data directly into the OAuth2 object
        sc = OAuth2(None, None, from_file=None)
        sc.access_token = db_data['access_token']
        sc.refresh_token = db_data['refresh_token']
        sc.consumer_key = db_data['consumer_key']
        sc.consumer_secret = db_data['consumer_secret']
        sc.token_time = db_data['token_time']
        
        # 3. Check validity and refresh if needed
        if not sc.token_is_valid():
            print("🔄 Token expired. Refreshing...")
            sc.refresh_access_token()
            
            # 4. Save the NEW tokens back to Supabase
            updated_payload = {
                "access_token": sc.access_token,
                "refresh_token": sc.refresh_token,
                "token_time": sc.token_time
            }
            supabase.table("auth_vault").update(updated_payload).eq("id", "yahoo_token").execute()
            print("✅ Supabase tokens updated.")
            
        return sc
    except Exception as e:
        print(f"❌ Auth Error: {e}")
        return None

def get_league_and_team_keys(sc):
    try:
        gm = yfa.Game(sc, 'nhl')
        game_id = gm.game_id()
        
        # Manual fetch for League
        url = f"https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1/games;game_keys={game_id}/leagues?format=json"
        data = sc.session.get(url).json()
        
        user_wrapper = data['fantasy_content']['users']['0']['user']
        leagues_wrapper = user_wrapper[1]['games']['0']['game'][1]['leagues']
        
        if leagues_wrapper['count'] == 0: return None, None, None

        league_id = leagues_wrapper['0']['league'][0]['league_key']
        
        # Manual fetch for Team
        team_url = f"https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1/games;game_keys={game_id}/leagues;league_keys={league_id}/teams?format=json"
        t_data = sc.session.get(team_url).json()
        
        base = t_data['fantasy_content']['users']['0']['user'][1]['games']['0']['game'][1]['leagues']['0']['league'][1]['teams']
        team_key = base['0']['team'][0][0]['team_key']
        
        return league_id, team_key, game_id
        
    except Exception as e:
        print(f"⚠️ Error finding keys: {e}")
        return None, None, None

def fetch_yahoo_data():
    print("🔌 Connecting to Yahoo via Supabase...")
    sc = connect_to_yahoo()
    if not sc: return

    print("✅ Authentication Successful!")
    l_key, t_key, g_id = get_league_and_team_keys(sc)
    
    if not l_key:
        print("❌ Could not find active league.")
        return

    print(f"🏆 League: {l_key} | 👤 Team: {t_key}")
    lg = yfa.League(sc, l_key)

    # 1. Get My Roster
    print("📥 Fetching Roster...")
    team = lg.to_team(t_key)
    roster = team.roster()
    df_roster = pd.DataFrame(roster)
    df_roster['Status'] = 'Rostered'
    
    # 2. Get Free Agents
    print("🦅 Scouting Waiver Wire...")
    fa_c = lg.free_agents('C')[:25]
    fa_lw = lg.free_agents('LW')[:25]
    fa_rw = lg.free_agents('RW')[:25]
    fa_d = lg.free_agents('D')[:25]
    
    free_agents = fa_c + fa_lw + fa_rw + fa_d
    df_fa = pd.DataFrame(free_agents)
    df_fa['Status'] = 'Free Agent'

    # 3. Combine & Save
    print("💾 Saving data to 'yahoo_export.csv'...")
    final_df = pd.concat([df_roster, df_fa], ignore_index=True)
    final_df.to_csv("yahoo_export.csv", index=False)
    print("✅ Done! Data ready for PuckNexus.")

if __name__ == "__main__":
    fetch_yahoo_data()