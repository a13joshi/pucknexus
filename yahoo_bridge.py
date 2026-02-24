import yahoo_fantasy_api as yfa
from yahoo_oauth import OAuth2
import pandas as pd
import json

def connect_to_yahoo():
    sc = OAuth2(None, None, from_file='oauth2.json')
    if not sc.token_is_valid():
        sc.refresh_access_token()
    return sc

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
    print("🔌 Connecting to Yahoo...")
    sc = connect_to_yahoo()
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
    
    # 2. Get Free Agents (Top available)
    print("🦅 Scouting Waiver Wire...")
    
    # 🟢 FIX: Removed 'count' argument. We fetch default and slice the list in Python.
    # The API returns the top available players by % Rostered/Rank.
    fa_c = lg.free_agents('C')[:25]
    fa_lw = lg.free_agents('LW')[:25]
    fa_rw = lg.free_agents('RW')[:25]
    fa_d = lg.free_agents('D')[:25]
    
    free_agents = fa_c + fa_lw + fa_rw + fa_d
                  
    df_fa = pd.DataFrame(free_agents)
    df_fa['Status'] = 'Free Agent'

    # 3. Combine & Save
    print("💾 Saving data to 'yahoo_export.csv'...")
    cols = ['name', 'position_type', 'eligible_positions', 'status', 'Status']
    
    final_df = pd.concat([df_roster, df_fa], ignore_index=True)
    
    # Save to CSV
    final_df.to_csv("yahoo_export.csv", index=False)
    print("✅ Done! You can now upload 'yahoo_export.csv' to PuckNexus.")

if __name__ == "__main__":
    fetch_yahoo_data()