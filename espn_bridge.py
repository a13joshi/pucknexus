import pandas as pd


def fetch_espn_data(league_id, year, espn_s2, swid, my_team_name=None):
    """
    Connects to an ESPN fantasy hockey league using browser cookies.
    Returns a DataFrame with the same schema as yahoo_bridge output:
      name, Status, Fantasy_Team, Manager, Is_Mine, match_key

    Args:
        league_id:    ESPN league ID (integer or string)
        year:         Season year (e.g. 2026)
        espn_s2:      espn_s2 browser cookie (from Chrome DevTools)
        swid:         SWID browser cookie (from Chrome DevTools)
        my_team_name: Exact team name string to flag Is_Mine=True
    """
    try:
        from espn_api.hockey import League
    except ImportError:
        raise ImportError("espn_api not installed. Run: pip install espn_api")

    league = League(
        league_id=int(league_id),
        year=int(year),
        espn_s2=espn_s2,
        swid=swid
    )

    all_players = []

    # Normalize SWID — add curly braces if user omitted them
    swid_clean = swid.strip()
    if not swid_clean.startswith('{'): swid_clean = '{' + swid_clean
    if not swid_clean.endswith('}'): swid_clean = swid_clean + '}'
    swid_normalized = swid_clean.upper()

    # Rostered players
    for team in league.teams:
        # Match by SWID — works regardless of whether user entered braces or not
        is_mine = any(
            owner.get('id', '').strip().upper() == swid_normalized
            for owner in team.owners
        ) if team.owners else False

        # Fallback: team name match if SWID didn't work
        if not is_mine and my_team_name:
            is_mine = team.team_name.strip().lower() == my_team_name.strip().lower()

        manager = (team.owners[0].get('firstName', '') + ' ' + team.owners[0].get('lastName', '')).strip() \
            if team.owners else 'Unknown'

        for player in team.roster:
            all_players.append({
                'name':         player.name,
                'Status':       'Rostered',
                'Fantasy_Team': team.team_name,
                'Manager':      manager.strip(),
                'Is_Mine':      is_mine,
                'match_key':    player.name.lower().strip()
            })

    # Free agents
    try:
        for player in league.free_agents(size=200):
            all_players.append({
                'name':         player.name,
                'Status':       'Free Agent',
                'Fantasy_Team': 'Available',
                'Manager':      'None',
                'Is_Mine':      False,
                'match_key':    player.name.lower().strip()
            })
    except Exception as e:
        print(f"⚠️ Could not fetch ESPN free agents: {e}")

    df = pd.DataFrame(all_players)
    df = df.drop_duplicates(subset=['match_key'])
    return df


def get_espn_league_cats(league_id, year, espn_s2, swid):
    """
    Fetches the scoring categories active in the ESPN league.
    Returns a list of PuckNexus category names, or None if undetectable.
    """
    # ESPN stat ID → PuckNexus internal column name
    ESPN_STAT_MAP = {
        1:   'G',
        2:   'A',
        3:   'PTS',
        4:   'PIM',
        5:   'PPG',
        6:   'PPA',
        7:   'PPP',
        8:   'SHG',
        9:   'SHA',
        10:  'SHP',
        11:  'GWG',
        12:  'SOG',
        13:  'SH%',
        14:  'HIT',
        15:  'BLK',
        16:  '+/-',
        17:  'FOW',
        19:  'W',
        20:  'L',
        21:  'SHO',
        22:  'SV',
        23:  'GA',
        24:  'GAA',
        25:  'SV%',
        26:  'GS',
    }

    SUPPORTED = {'G', 'A', '+/-', 'PIM', 'PPP', 'SOG', 'HIT', 'BLK',
                 'W', 'GAA', 'SV%', 'SHO', 'GWG', 'SHP', 'TOI',
                 'SV', 'GA', 'SA', 'L'}

    try:
        from espn_api.hockey import League
        league = League(
            league_id=int(league_id),
            year=int(year),
            espn_s2=espn_s2,
            swid=swid
        )

        scoring_settings = league.settings.scoring_format
        cats = []
        for stat in scoring_settings:
            stat_id = getattr(stat, 'statId', None) or getattr(stat, 'id', None)
            if stat_id and stat_id in ESPN_STAT_MAP:
                cat = ESPN_STAT_MAP[stat_id]
                if cat in SUPPORTED:
                    cats.append(cat)

        return cats if cats else None

    except Exception as e:
        print(f"⚠️ Could not fetch ESPN league cats: {e}")
        return None