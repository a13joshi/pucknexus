import streamlit as st
import os
import pandas as pd
import warnings
from datetime import datetime, timedelta, date

warnings.filterwarnings("ignore", category=SyntaxWarning)

# ── Inject secrets into env BEFORE importing supabase ────────────────────────
try:
    if "SUPABASE_URL" in st.secrets: os.environ["SUPABASE_URL"] = st.secrets["SUPABASE_URL"]
    if "SUPABASE_KEY" in st.secrets: os.environ["SUPABASE_KEY"] = st.secrets["SUPABASE_KEY"]
except Exception:
    pass

from supabase_config import supabase
from data_fetcher import get_nhl_skater_stats, get_nhl_goalie_stats, get_nhl_schedule, get_fantasy_weeks, get_multi_week_schedule, get_blended_projections
from goalie_intel import get_todays_goalies, calculate_sos_score, get_goalie_streaming_ranks, GOALIE_RESOURCES
from monster_math import calculate_z_scores
from config import SUPPORTED_CATS, GOALIE_CATS, DEFAULT_CATS, DEFAULT_G_CATS, get_team_logo, get_headshot

# Tab renderers
from tabs import dashboard, schedule, war_room, trends, wire_hawk, power_rankings, matchup
from tabs import goalie_intel_tab, playoff_primer

# ── Cached data loaders ───────────────────────────────────────────────────────
@st.cache_data
def load_skaters(season, start_date, end_date=None):
    return get_nhl_skater_stats(season, start_date, end_date)

@st.cache_data
def load_goalies(season, start_date, end_date=None):
    return get_nhl_goalie_stats(season, start_date, end_date)

# ── Page config & global CSS ──────────────────────────────────────────────────
st.set_page_config(page_title="PuckNexus", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    h1 {
        font-family: 'Helvetica Neue', sans-serif;
        text-transform: uppercase; font-weight: 900; letter-spacing: 2px;
        background: -webkit-linear-gradient(45deg, #FF4B4B, #FF914D);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    div[data-testid="stMetric"] {
        background-color: #1c1f26; padding: 20px;
        border-radius: 10px; border-left: 5px solid #FF4B4B;
    }
    .stAlert { border: none; background-color: #1c1f26; color: white; }
    [data-testid="stMetricValue"] { font-size: 32px; font-weight: 700; color: #FF914D; }
</style>
""", unsafe_allow_html=True)

st.title("PUCKNEXUS")
st.caption("THE UNOFFICIAL FANTASY HOCKEY EXPANSION")

# ── Category setup ────────────────────────────────────────────────────────────
raw_cats = st.session_state.get('league_cats', DEFAULT_CATS + DEFAULT_G_CATS)
raw_cats = [c for c in raw_cats if c in SUPPORTED_CATS]
cats   = [c for c in raw_cats if c not in GOALIE_CATS] or DEFAULT_CATS
g_cats = [c for c in raw_cats if c in GOALIE_CATS]     or DEFAULT_G_CATS
all_strategy_cats = cats + g_cats
weights = {cat: 1.0 for cat in all_strategy_cats}  # default, overridden below

# ── Global Control Center ─────────────────────────────────────────────────────
with st.expander("📡 GLOBAL CONTROL CENTER & LEAGUE SYNC", expanded=True):
    col_cfg, col_strat, col_sync = st.columns([1, 1.5, 1.5])

    with col_cfg:
        st.markdown("### ⚙️ Engine Settings")
        season_choice = st.selectbox("Season", ["20252026", "20242025", "20232024"])
        timeframe     = st.selectbox("📅 Timeframe", ["Full Season", "Last 14 Days", "Last 30 Days", "Custom Date Range"])
        projection_mode = st.radio("📊 Projection Mode", ["Season Stats", "Blended ROS"], horizontal=True,
                                   help="Blended ROS: 65% last 21 days + 35% season average")

        stats_start_date = stats_end_date = None
        if timeframe == "Last 14 Days":
            stats_start_date = str(date.today() - timedelta(days=14))
        elif timeframe == "Last 30 Days":
            stats_start_date = str(date.today() - timedelta(days=30))
        elif timeframe == "Custom Date Range":
            date_range = st.date_input("Select Date Range", value=(date.today() - timedelta(days=7), date.today()))
            if len(date_range) == 2:
                stats_start_date = str(date_range[0])
                stats_end_date   = str(date_range[1])

    with col_strat:
        st.markdown("### 🧠 Strategy Weights")
        st.caption("Select categories to punt (sets value to 0).")
        punt_cats = st.multiselect("🗑️ Punt Categories", options=all_strategy_cats, label_visibility="collapsed")
        weights   = {cat: 0.0 if cat in punt_cats else 1.0 for cat in all_strategy_cats}

    with col_sync:
        st.markdown("### 🏒 League Sync")
        from yahoo_bridge import get_yahoo_auth_url, exchange_code_for_token, get_user_leagues, fetch_yahoo_data, get_league_cats

        platform = st.radio("Platform", ["Yahoo", "ESPN"], horizontal=True, key="platform_choice")

        if platform == "Yahoo":
            if "code" in st.query_params and 'yahoo_token_data' not in st.session_state:
                with st.spinner("Authenticating..."):
                    try:
                        st.session_state['yahoo_token_data'] = exchange_code_for_token(st.query_params["code"])
                        st.session_state['available_leagues'] = get_user_leagues()
                        st.query_params.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Login failed: {e}")

            if 'yahoo_token_data' not in st.session_state:
                try:
                    st.link_button("🟣 Login with Yahoo", get_yahoo_auth_url(), use_container_width=True)
                    st.caption("Securely connect to pull live rosters.")
                except Exception as e:
                    st.error(f"Streamlit Vault Error: Missing {e} in secrets.")
            else:
                leagues_dict = st.session_state.get('available_leagues', {})
                if leagues_dict:
                    selected_league_name = st.selectbox("Active League", options=list(leagues_dict.keys()), label_visibility="collapsed")
                    c_sync, c_dis = st.columns(2)
                    with c_sync:
                        if st.button("🔄 Sync Data", use_container_width=True):
                            with st.spinner("Pulling fresh data..."):
                                yahoo_df    = fetch_yahoo_data(leagues_dict[selected_league_name])
                                league_cats = get_league_cats(leagues_dict[selected_league_name])
                                if league_cats:
                                    st.session_state['league_cats'] = league_cats
                                if yahoo_df is None or yahoo_df.empty:
                                    st.error("Sync failed — no data returned.")
                                else:
                                    st.session_state['yahoo_data']    = yahoo_df
                                    st.session_state['sync_platform'] = 'Yahoo'
                                    guid = st.session_state['yahoo_token_data'].get('guid', 'unknown')
                                    if supabase:
                                        try:
                                            records = yahoo_df.astype(str).to_dict(orient='records')
                                            for rec in records: rec['guid'] = guid
                                            supabase.table('yahoo_league_cache').delete().eq('guid', guid).execute()
                                            supabase.table('yahoo_league_cache').insert(records).execute()
                                        except Exception as e:
                                            print(f"⚠️ Cache save failed: {e}")
                                    st.success("Synced!")
                                    st.rerun()
                    with c_dis:
                        if st.button("Disconnect", type="tertiary", use_container_width=True):
                            del st.session_state['yahoo_token_data']
                            st.rerun()
                else:
                    st.warning("No hockey leagues found.")

        else:  # ESPN
            from espn_bridge import fetch_espn_data, get_espn_league_cats
            st.caption("Cookies found in Chrome DevTools → Application → Cookies → espn.com")
            espn_lid  = st.text_input("ESPN League ID", key="espn_lid")
            espn_year = st.text_input("Season Year", value="2026", key="espn_year")
            espn_s2   = st.text_input("espn_s2 cookie", type="password", key="espn_s2")
            espn_swid = st.text_input("SWID cookie (curly braces optional)", type="password", key="espn_swid")
            st.caption("Your team is auto-detected from your SWID.")

            if st.button("🔄 Sync ESPN League", use_container_width=True):
                if espn_lid and espn_s2 and espn_swid:
                    with st.spinner("Connecting to ESPN..."):
                        try:
                            espn_df     = fetch_espn_data(espn_lid, espn_year, espn_s2, espn_swid)
                            league_cats = get_espn_league_cats(espn_lid, espn_year, espn_s2, espn_swid)
                            if league_cats:
                                st.session_state['league_cats'] = league_cats
                            st.session_state['yahoo_data']    = espn_df
                            st.session_state['sync_platform'] = 'ESPN'
                            st.success(f"ESPN synced: {len(espn_df)} players loaded.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"ESPN sync failed: {e}")
                else:
                    st.warning("Please fill in League ID, espn_s2, and SWID.")

    selected_pos = st.multiselect(
        "Position Filter", ['C', 'L', 'R', 'D', 'G'],
        default=['C', 'L', 'R', 'D', 'G'], key="global_pos_filter"
    )

st.divider()

# ── Restore Yahoo data from Supabase on fresh session ────────────────────────
if 'yahoo_data' not in st.session_state and 'yahoo_token_data' in st.session_state:
    guid = st.session_state['yahoo_token_data'].get('guid')
    if guid:
        try:
            cached = supabase.table('yahoo_league_cache').select('*').eq('guid', guid).execute()
            if cached.data:
                st.session_state['yahoo_data'] = pd.DataFrame(cached.data)
        except Exception:
            pass

# ── Global data loading ───────────────────────────────────────────────────────
calc_season     = season_choice
calc_start_date = stats_start_date if stats_start_date else None
calc_end_date   = stats_end_date   if stats_end_date   else None

s_df_global = load_skaters(calc_season, calc_start_date, calc_end_date)
g_df_global = load_goalies(calc_season, calc_start_date, calc_end_date)

# Apply blended projections if mode is active (replaces skater stats for scoring only)
if projection_mode == "Blended ROS" and timeframe == "Full Season":
    with st.spinner("🔀 Building blended ROS projections..."):
        blended = get_blended_projections(calc_season)
        if not blended.empty:
            # Preserve Team/Pos/playerId from season data, replace stat columns
            stat_cols = ['G', 'A', '+/-', 'PIM', 'PPP', 'SOG', 'HIT', 'BLK', 'SHP', 'GWG']
            meta_cols = ['Player', 'playerId', 'Team', 'Pos', 'GP']
            for c in stat_cols:
                if c in blended.columns and c in s_df_global.columns:
                    s_df_global = s_df_global.copy()
                    merge_tmp = blended[['Player', c]].rename(columns={c: f"{c}_blended"})
                    s_df_global = pd.merge(s_df_global, merge_tmp, on='Player', how='left')
                    s_df_global[c] = s_df_global[f"{c}_blended"].fillna(s_df_global[c])
                    s_df_global = s_df_global.drop(columns=[f"{c}_blended"])
            st.caption("📊 **Blended ROS Mode active** — stats reflect 65% recent pace + 35% season average.")

if timeframe != "Full Season":
    s_base = load_skaters(calc_season, None, None)
    if not s_df_global.empty and not s_base.empty:
        missing_s = [c for c in ['Team', 'playerId', 'Pos'] if c not in s_df_global.columns and c in s_base.columns]
        if missing_s:
            s_df_global = pd.merge(s_df_global, s_base[['Player'] + missing_s].drop_duplicates('Player'), on='Player', how='left')
    g_base = load_goalies(calc_season, None, None)
    if not g_df_global.empty and not g_base.empty:
        missing_g = [c for c in ['Team', 'playerId'] if c not in g_df_global.columns and c in g_base.columns]
        if missing_g:
            g_df_global = pd.merge(g_df_global, g_base[['Player'] + missing_g].drop_duplicates('Player'), on='Player', how='left')

# ── NexusScore calculation ────────────────────────────────────────────────────
min_gp       = 5 if timeframe == "Full Season" else 1
active_cats  = [c for c in cats if weights.get(c, 0) > 0]
num_active_cats = max(len(active_cats), 1)

# Goalie math
if not g_df_global.empty:
    g_min_gp       = 12 if timeframe == "Full Season" else 3
    g_df_math_pool = g_df_global[g_df_global['GP'] >= g_min_gp]
    g_pass_1 = calculate_z_scores(g_df_math_pool, {'W': False, 'GAA': True, 'SV%': False, 'SHO': False})
    if 'Total Z' in g_pass_1.columns:
        top_g = g_pass_1.nlargest(40, 'Total Z')['Player'].tolist()
        evaluated_goalies = calculate_z_scores(
            g_df_math_pool[g_df_math_pool['Player'].isin(top_g)],
            {'W': False, 'GAA': True, 'SV%': False, 'SHO': False}
        )
        evaluated_goalies['Total Z'] = evaluated_goalies['Total Z'] * (num_active_cats / 4.0)
        evaluated_goalies = evaluated_goalies.rename(columns={'Total Z': 'NexusScore'})
        evaluated_goalies['match_key'] = evaluated_goalies['Player'].str.lower().str.strip()
        restore_g = [c for c in ['playerId', 'Team'] if c not in evaluated_goalies.columns and c in g_df_global.columns]
        if restore_g:
            evaluated_goalies = pd.merge(evaluated_goalies, g_df_global[['Player'] + restore_g].drop_duplicates('Player'), on='Player', how='left')
    else:
        evaluated_goalies = pd.DataFrame()
else:
    evaluated_goalies = pd.DataFrame()

# Skater math
if not s_df_global.empty:
    s_df_math_pool = s_df_global[s_df_global['GP'] >= min_gp]
    s_pass_1 = calculate_z_scores(s_df_math_pool, weights)
    if 'Total Z' in s_pass_1.columns:
        top_s = s_pass_1.nlargest(300, 'Total Z')['Player'].tolist()
        evaluated_df = calculate_z_scores(s_df_math_pool[s_df_math_pool['Player'].isin(top_s)], weights)
        evaluated_df = evaluated_df.rename(columns={'Total Z': 'NexusScore'})
        evaluated_df['match_key'] = evaluated_df['Player'].str.lower().str.strip()
        restore_s = [c for c in ['playerId', 'Team'] if c not in evaluated_df.columns and c in s_df_global.columns]
        if restore_s:
            evaluated_df = pd.merge(evaluated_df, s_df_global[['Player'] + restore_s].drop_duplicates('Player'), on='Player', how='left')
    else:
        st.error("Error: 'Total Z' column not generated. Check monster_math.py.")
        st.stop()
else:
    evaluated_df = pd.DataFrame()

if evaluated_df.empty:
    st.error("No skater data available. Check your NHL API connection.")
    st.stop()

# Build combined final DataFrame (used by dashboard, war_room, wire_hawk)
if not evaluated_goalies.empty and 'Pos' not in evaluated_goalies.columns:
    evaluated_goalies['Pos'] = 'G'

if not evaluated_df.empty and not evaluated_goalies.empty:
    final = pd.concat([evaluated_df, evaluated_goalies], ignore_index=True)
elif not evaluated_df.empty:
    final = evaluated_df.copy()
else:
    final = pd.DataFrame()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
    "📊 DASHBOARD", "📅 SCHEDULE", "⚖️ WAR ROOM", "📈 TRENDS",
    "🦅 WIRE HAWK", "🏆 POWER RANKINGS", "⚔️ MATCHUP",
    "🥅 GOALIE INTEL", "🔮 PLAYOFF PRIMER"
])

dashboard.render(tab1, final, evaluated_df, evaluated_goalies, cats, g_cats, weights, selected_pos)
schedule.render(tab2)
war_room.render(tab3, final, cats, weights)
trends.render(tab4, calc_season, cats, weights, selected_pos)
wire_hawk.render(tab5, final, cats, weights)
power_rankings.render(tab6, evaluated_df, evaluated_goalies, cats, weights)
matchup.render(tab7, s_df_global, g_df_global, cats, g_cats, weights, calc_season, timeframe, projection_mode)
goalie_intel_tab.render(tab8, g_df_global)
playoff_primer.render(tab9)