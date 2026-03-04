import os
import json
import pandas as pd
import xml.etree.ElementTree as ET
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
from supabase_config import supabase

def _get_yahoo_oauth_session():
    """Helper function to securely authenticate and return the OAuth session."""
    temp_oauth_file = 'temp_oauth.json'

    # 1. Retrieve tokens from Supabase Auth Vault
    try:
        response = supabase.table("auth_vault").select("*").eq("id", "yahoo_token").execute()
        if not response.data:
            raise Exception("Yahoo tokens not found in Supabase Auth Vault.")
        
        token_data = response.data[0]
        
        with open(temp_oauth_file, 'w') as f:
            json.dump(token_data, f)
            
    except Exception as e:
        raise Exception(f"Failed to load Auth Vault: {e}")

    # 2. Authenticate
    sc = OAuth2(None, None, from_file=temp_oauth_file)
    
    # --- Token Persistence ---
    with open(temp_oauth_file, 'r') as f:
        current_tokens = json.load(f)
    
    if current_tokens.get('access_token') != token_data.get('access_token'):
        print("🔄 Token refreshed! Saving to Supabase Auth Vault IMMEDIATELY...")
        current_tokens['id'] = 'yahoo_token'
        supabase.table("auth_vault").upsert(current_tokens).execute()
        print("✅ Supabase Auth Vault secured.")
        
    return sc, temp_oauth_file


def get_user_leagues():
    """
    Step 1: Fetches NHL leagues associated with the Yahoo account.
    Returns a dictionary: {"League Name": "league_key"}
    """
    sc = None
    temp_oauth_file = None
    try:
        sc, temp_oauth_file = _get_yahoo_oauth_session()
        
        print("🔍 Fetching your NHL leagues...")
        res = sc.session.get("https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1/games;game_keys=nhl/leagues")
        
        if res.status_code != 200:
            raise Exception(f"Yahoo API Error: {res.status_code} - {res.text}")
            
        root = ET.fromstring(res.text)
        ns = {'ns': 'http://fantasysports.yahooapis.com/fantasy/v2/base.rng'}
        
        leagues_dict = {}
        for league in root.findall('.//ns:league', ns):
            l_key = league.find('ns:league_key', ns).text
            l_name = league.find('ns:name', ns).text
            leagues_dict[l_name] = l_key

        if not leagues_dict:
            raise Exception("No active NHL leagues found for this account.")
            
        return leagues_dict
        
    finally:
        # Always clean up the local token file
        if temp_oauth_file and os.path.exists(temp_oauth_file):
            os.remove(temp_oauth_file)


def fetch_yahoo_data(selected_league_key):
    """
    Step 2: Fetches roster and free agent data for a specific league and exports to CSV.
    """
    sc = None
    temp_oauth_file = None
    try:
        sc, temp_oauth_file = _get_yahoo_oauth_session()
        
        print(f"\n🏆 Connecting to league key: {selected_league_key}...")
        
        # Initialize the chosen league
        gm = yfa.Game(sc, 'nhl')
        lg = gm.to_league(selected_league_key)

        all_players = []

        # Loop through ALL Teams in the selected league
        print("🔄 Fetching rosters for all teams...")
        teams = lg.teams()
        
        for team_key, team_data in teams.items():
            team_name = team_data.get('name', 'Unknown Team')
            manager_name = team_data.get('managers', [{}])[0].get('manager', {}).get('nickname', 'Unknown GM')
            
            team_obj = lg.to_team(team_key)
            try:
                roster = team_obj.roster()
                for p in roster:
                    all_players.append({
                        'name': p['name'],
                        'Status': 'Rostered',
                        'Fantasy_Team': team_name,
                        'Manager': manager_name,
                        'match_key': p['name'].lower().strip()
                    })
            except Exception as e:
                print(f"⚠️ Could not fetch roster for {team_name}: {e}")

        print(f"✅ Found {len([p for p in all_players if p['Status'] == 'Rostered'])} rostered players.")

        # Fetch Top Free Agents
        print("🔄 Fetching top Free Agents...")
        try:
            positions_to_check = ['C', 'LW', 'RW', 'D', 'G']
            for pos in positions_to_check:
                free_agents = lg.free_agents(pos)
                for p in free_agents[:20]:
                    all_players.append({
                        'name': p['name'],
                        'Status': 'Free Agent',
                        'Fantasy_Team': 'Available',
                        'Manager': 'None',
                        'match_key': p['name'].lower().strip()
                    })
        except Exception as e:
            print(f"⚠️ Issue fetching free agents: {e}")

        # Export to CSV for app.py
        df = pd.DataFrame(all_players)
        df = df.drop_duplicates(subset=['match_key'])
        df.to_csv("yahoo_export.csv", index=False)
        print("💾 Global League Sync complete. Saved to yahoo_export.csv.")

    finally:
        # Always clean up the local token file
        if temp_oauth_file and os.path.exists(temp_oauth_file):
            os.remove(temp_oauth_file)