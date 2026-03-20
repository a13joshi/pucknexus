import os
import json
import time
import requests
import base64
import pandas as pd
import xml.etree.ElementTree as ET
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
import streamlit as st

def get_yahoo_auth_url():
    """Generates the secure Yahoo login URL."""
    client_id = st.secrets["YAHOO_CLIENT_ID"]
    redirect_uri = st.secrets["YAHOO_REDIRECT_URI"]
    return f"https://api.login.yahoo.com/oauth2/request_auth?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&language=en-us"

def exchange_code_for_token(auth_code):
    """Exchanges the redirect code for a secure access token."""
    client_id = st.secrets["YAHOO_CLIENT_ID"]
    client_secret = st.secrets["YAHOO_CLIENT_SECRET"]
    redirect_uri = st.secrets["YAHOO_REDIRECT_URI"]
    
    token_url = "https://api.login.yahoo.com/oauth2/get_token"
    
    # Yahoo requires Basic Auth for the token exchange
    auth_str = f"{client_id}:{client_secret}"
    b64_auth = base64.b64encode(auth_str.encode()).decode()
    headers = {"Authorization": f"Basic {b64_auth}", "Content-Type": "application/x-www-form-urlencoded"}
    data = {"client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect_uri, "code": auth_code, "grant_type": "authorization_code"}
    
    response = requests.post(token_url, headers=headers, data=data)
    if response.status_code != 200:
        raise Exception(f"Failed to get token: {response.text}")
        
    token_data = response.json()
    
    # Format into the exact structure the yahoo_oauth library expects
    return {
        "access_token": token_data["access_token"],
        "consumer_key": client_id,
        "consumer_secret": client_secret,
        "guid": token_data.get("xoauth_yahoo_guid"),
        "refresh_token": token_data["refresh_token"],
        "token_time": time.time(),
        "token_type": "bearer"
    }

def _get_yahoo_oauth_session():
    """Silently builds the OAuth2 object using Streamlit's session memory."""
    if 'yahoo_token_data' not in st.session_state:
        raise Exception("User is not authenticated.")
        
    temp_oauth_file = 'temp_oauth.json'
    with open(temp_oauth_file, 'w') as f:
        json.dump(st.session_state['yahoo_token_data'], f)
        
    sc = OAuth2(None, None, from_file=temp_oauth_file)
    
    # If the token expired and refreshed itself, save the new one back to session memory!
    with open(temp_oauth_file, 'r') as f:
        current_tokens = json.load(f)
    if current_tokens['access_token'] != st.session_state['yahoo_token_data']['access_token']:
        st.session_state['yahoo_token_data'] = current_tokens
        
    return sc, temp_oauth_file

def get_user_leagues():
    """Fetches NHL leagues for the dropdown."""
    sc, temp_oauth_file = _get_yahoo_oauth_session()
    try:
        res = sc.session.get("https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1/games;game_keys=nhl/leagues")
        root = ET.fromstring(res.text)
        ns = {'ns': 'http://fantasysports.yahooapis.com/fantasy/v2/base.rng'}
        
        leagues_dict = {}
        for league in root.findall('.//ns:league', ns):
            leagues_dict[league.find('ns:name', ns).text] = league.find('ns:league_key', ns).text
        return leagues_dict
    finally:
        if os.path.exists(temp_oauth_file): os.remove(temp_oauth_file)

# Yahoo stat ID → PuckNexus internal column name
YAHOO_STAT_MAP = {
    '1':  'G',
    '2':  'A',
    '4':  '+/-',
    '5':  'PIM',
    '6':  'PPG',
    '7':  'PPA',
    '8':  'PPP',
    '9':  'SHG',
    '10': 'SHA',
    '11': 'SHP',
    '12': 'GWG',
    '13': 'SOG',
    '14': 'SOG',
    '15': 'SH%',
    '16': 'FW',
    '18': 'GS',
    '19': 'W',
    '20': 'L',
    '21': 'SHO',
    '22': 'GA',
    '23': 'GAA',
    '24': 'SV%',
    '25': 'SV',
    '26': 'SHO',
    '27': 'SA',
    '28': 'TOI',
    '31': 'HIT',
    '32': 'BLK',
}

def get_league_end_date(selected_league_key):
    """
    Fetches the last week of the regular season (excluding playoffs) from Yahoo league settings.
    Returns a date object representing the last day of the last regular season fantasy week,
    or None if unavailable.
    """
    sc, temp_oauth_file = _get_yahoo_oauth_session()
    try:
        res = sc.session.get(
            f"https://fantasysports.yahooapis.com/fantasy/v2/league/{selected_league_key}/settings"
        )
        root = ET.fromstring(res.text)
        ns = {'ns': 'http://fantasysports.yahooapis.com/fantasy/v2/base.rng'}

        # end_week is the last week of the fantasy regular season
        end_week_el = root.find('.//ns:end_week', ns)
        if end_week_el is None:
            return None

        end_week_num = int(end_week_el.text)

        # Map week number to actual date using our fantasy week generator
        from data_fetcher import get_fantasy_weeks
        weeks = get_fantasy_weeks()

        if end_week_num <= len(weeks):
            return weeks[end_week_num - 1]['end']
        return None

    except Exception as e:
        print(f"⚠️ Could not fetch league end date: {e}")
        return None
    finally:
        if os.path.exists(temp_oauth_file):
            os.remove(temp_oauth_file)


def get_league_cats(selected_league_key):
    """Fetches the scoring categories active in the user's league."""
    sc, temp_oauth_file = _get_yahoo_oauth_session()
    try:
        res = sc.session.get(
            f"https://fantasysports.yahooapis.com/fantasy/v2/league/{selected_league_key}/settings"
        )
        root = ET.fromstring(res.text)
        ns = {'ns': 'http://fantasysports.yahooapis.com/fantasy/v2/base.rng'}
        
        active_cats = []
        for stat in root.findall('.//ns:stat', ns):
            stat_id = stat.findtext('ns:stat_id', namespaces=ns)
            enabled = stat.findtext('ns:enabled', namespaces=ns)
            if enabled == '1' and stat_id in YAHOO_STAT_MAP:
                active_cats.append(YAHOO_STAT_MAP[stat_id])
        
        return active_cats if active_cats else None
    except Exception as e:
        print(f"⚠️ Could not fetch league cats: {e}")
        return None
    finally:
        if os.path.exists(temp_oauth_file): os.remove(temp_oauth_file)

def fetch_yahoo_data(selected_league_key):
    """Pulls roster and free agent data, accurately identifying the user's specific team."""
    sc, temp_oauth_file = _get_yahoo_oauth_session()
    try:
        gm = yfa.Game(sc, 'nhl')
        lg = gm.to_league(selected_league_key)
        
        # FIX 3: Safely get the Team Key by specifically filtering for NHL (Bypasses the library crash)
        my_team_key = None
        try:
            res = sc.session.get("https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1/games;game_keys=nhl/teams")
            if res.status_code == 200:
                root = ET.fromstring(res.text)
                ns = {'ns': 'http://fantasysports.yahooapis.com/fantasy/v2/base.rng'}
                for team in root.findall('.//ns:team', ns):
                    t_key = team.find('ns:team_key', ns).text
                    if t_key and t_key.startswith(selected_league_key):
                        my_team_key = t_key
                        break
        except Exception as e:
            print(f"Warning: Could not isolate manager's team key: {e}")

        all_players = []

        # Fetch Rosters
        teams = lg.teams()
        for team_key, team_data in teams.items():
            team_name = team_data.get('name', 'Unknown Team')
            manager_name = team_data.get('managers', [{}])[0].get('manager', {}).get('nickname', 'Unknown GM')
            
            # Identify if this team belongs to the logged-in user
            is_my_team = (team_key == my_team_key)
            
            try:
                for p in lg.to_team(team_key).roster():
                    all_players.append({
                        'name': p['name'], 'Status': 'Rostered', 'Fantasy_Team': team_name,
                        'Manager': manager_name, 'Is_Mine': is_my_team, 'match_key': p['name'].lower().strip()
                    })
            except Exception as e:
                pass

        # Fetch Free Agents
        try:
            for pos in ['C', 'LW', 'RW', 'D', 'G']:
                for p in lg.free_agents(pos)[:20]:
                    all_players.append({
                        'name': p['name'], 'Status': 'Free Agent', 'Fantasy_Team': 'Available',
                        'Manager': 'None', 'Is_Mine': False, 'match_key': p['name'].lower().strip()
                    })
        except Exception as e:
            pass

        df = pd.DataFrame(all_players)
        df = df.drop_duplicates(subset=['match_key'])
        return df

    except Exception as e:
        print(f"❌ fetch_yahoo_data crashed: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if os.path.exists(temp_oauth_file): os.remove(temp_oauth_file)