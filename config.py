import pandas as pd

# ── Scoring categories ────────────────────────────────────────────────────────
SUPPORTED_CATS = {
    'G', 'A', '+/-', 'PIM', 'PPP', 'SOG', 'HIT', 'BLK',
    'W', 'GAA', 'SV%', 'SHO', 'GWG', 'SHP', 'TOI',
    'SV', 'GA', 'SA', 'L'
}
GOALIE_CATS   = {'W', 'GAA', 'SV%', 'SHO', 'GA', 'SA', 'SV', 'GS', 'L'}
DEFAULT_CATS  = ['G', 'A', '+/-', 'PIM', 'PPP', 'SOG', 'HIT', 'BLK']
DEFAULT_G_CATS = ['W', 'GAA', 'SV%', 'SHO']

# ── Team logo helper ──────────────────────────────────────────────────────────
_LOGO_MAP = {
    "NJD": "nj", "SJS": "sj", "LAK": "la",
    "UTA": "utah", "VEG": "vgk", "VGK": "vgk", "MTL": "mtl",
    "CGY": "cgy", "WPG": "wpg",
    "TBL": "lightning",
    "WSH": "capitals",
}

def get_team_logo(team_abbr):
    if not team_abbr or pd.isna(team_abbr):
        return ""
    code = _LOGO_MAP.get(str(team_abbr).upper(), str(team_abbr).lower())
    return f"https://a.espncdn.com/combiner/i?img=/i/teamlogos/nhl/500/{code}.png&h=40&w=40"

# ── Player headshot helper ────────────────────────────────────────────────────
def get_headshot(row):
    try:
        pid  = row.get('playerId')
        team = row.get('Team')
        if pd.isna(pid) or not pid:
            return ""
        return f"https://assets.nhle.com/mugs/nhl/20242025/{str(team).upper()}/{str(int(float(pid)))}.png"
    except Exception:
        return ""
