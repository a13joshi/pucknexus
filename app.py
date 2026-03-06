import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta, date
import warnings
warnings.filterwarnings("ignore", category=SyntaxWarning)

from data_fetcher import get_nhl_skater_stats, get_nhl_goalie_stats, get_nhl_schedule, get_fantasy_weeks
from monster_math import calculate_z_scores

# --- HELPER FUNCTIONS ---
@st.cache_data
def load_skaters(season, start_date, end_date=None):
    return get_nhl_skater_stats(season, start_date, end_date)

@st.cache_data
def load_goalies(season, start_date, end_date=None):
    return get_nhl_goalie_stats(season, start_date, end_date)

def get_team_logo(team_abbr):
    if not team_abbr or pd.isna(team_abbr): return ""
    logo_map = {"NJD": "nj", "SJS": "sj", "TBL": "tb", "LAK": "la", "UTA": "utah", "VEG": "vgk", "VGK": "vgk", "MTL": "mtl", "WSH": "wsh", "CGY": "cgy", "WPG": "wpg"}
    code = logo_map.get(str(team_abbr).upper(), str(team_abbr).lower())
    return f"https://a.espncdn.com/combiner/i?img=/i/teamlogos/nhl/500/{code}.png&h=40&w=40"

def get_headshot(row):
    try:
        pid, team = row.get('playerId'), row.get('Team')
        if pd.isna(pid) or not pid: return "" 
        return f"https://assets.nhle.com/mugs/nhl/20242025/{str(team).upper()}/{str(int(float(pid)))}.png"
    except: return ""

# --- GLOBAL CONFIG ---
st.set_page_config(page_title="PuckNexus", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    h1 { font-family: 'Helvetica Neue', sans-serif; text-transform: uppercase; font-weight: 900; letter-spacing: 2px; background: -webkit-linear-gradient(45deg, #FF4B4B, #FF914D); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    div[data-testid="stMetric"] { background-color: #1c1f26; padding: 20px; border-radius: 10px; border-left: 5px solid #FF4B4B; }
    
    /* Style for the Scout Recommendation and Verdicts */
    .stAlert {
        border: none;
        background-color: #1c1f26;
        color: white;
    }
    
    /* Make metrics pop */
    [data-testid="stMetricValue"] {
        font-size: 32px;
        font-weight: 700;
        color: #FF914D;
    }        
</style>
""", unsafe_allow_html=True)

st.title("PUCKNEXUS")
st.caption("THE UNOFFICIAL FANTASY HOCKEY EXPANSION")

# --- GLOBAL CONTROL CENTER (Replaces Sidebar) ---
cats = ['G', 'A', '+/-', 'PIM', 'PPP', 'SOG', 'HIT', 'BLK']

# This expander acts as a dropdown menu at the top of the page
with st.expander("📡 GLOBAL CONTROL CENTER & YAHOO SYNC", expanded=True):
    col_cfg, col_strat, col_yahoo = st.columns([1, 1.5, 1.5])

    with col_cfg:
        st.markdown("### ⚙️ Engine Settings")
        # 1. Expand the season selection
        season_choice = st.selectbox("Season", ["20252026", "20242025", "20232024"])
        
        # 2. Add the Custom Date Range option
        timeframe = st.selectbox("📅 Timeframe", ["Full Season", "Last 14 Days", "Last 30 Days", "Custom Date Range"])
        
        stats_start_date = None
        stats_end_date = None
        
        if timeframe == "Last 14 Days": 
            stats_start_date = str(date.today() - timedelta(days=14))
        elif timeframe == "Last 30 Days": 
            stats_start_date = str(date.today() - timedelta(days=30))
        elif timeframe == "Custom Date Range":
            # Streamlit opens a calendar widget when a tuple is passed as the value
            date_range = st.date_input("Select Date Range", value=(date.today() - timedelta(days=7), date.today()))
            
            # Ensure the user has actually selected both a start and end date on the calendar
            if len(date_range) == 2:
                stats_start_date = str(date_range[0])
                stats_end_date = str(date_range[1])

    with col_strat:
        st.markdown("### 🧠 Strategy Weights")
        st.caption("Select categories to punt (sets value to 0).")
        punt_cats = st.multiselect("🗑️ Punt Categories", options=cats, label_visibility="collapsed")
        
        # Streamlined weights logic: If it's punted, it's 0. Otherwise, it's 1.
        weights = {cat: 0.0 if cat in punt_cats else 1.0 for cat in cats}

    with col_yahoo:
        st.markdown("### 🦅 Yahoo Live Sync")
        from yahoo_bridge import get_yahoo_auth_url, exchange_code_for_token, get_user_leagues, fetch_yahoo_data
        
        # 1. Catch the OAuth Redirect Code from Yahoo
        if "code" in st.query_params and 'yahoo_token_data' not in st.session_state:
            auth_code = st.query_params["code"]
            with st.spinner("Authenticating..."):
                try:
                    st.session_state['yahoo_token_data'] = exchange_code_for_token(auth_code)
                    st.session_state['available_leagues'] = get_user_leagues()
                    st.query_params.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Login failed: {e}")

        # 2. Yahoo UI State Machine
        if 'yahoo_token_data' not in st.session_state:
            try:
                auth_url = get_yahoo_auth_url()
                
                # Reverting to the native button due to Streamlit Cloud sandbox limits
                st.link_button("🟣 Login with Yahoo", auth_url, use_container_width=True)
                
                st.caption("Securely connect to pull live rosters. (This will open a new, authenticated tab).")
            except Exception as e:
                st.error(f"Streamlit Vault Error: Missing {e} in secrets.")
        else:
            leagues_dict = st.session_state.get('available_leagues', {})
            if leagues_dict:
                selected_league_name = st.selectbox("Active League", options=list(leagues_dict.keys()), label_visibility="collapsed")
                
                c_sync, c_dis = st.columns(2)
                with c_sync:
                    if st.button(f"🔄 Sync Data", use_container_width=True):
                        with st.spinner("Pulling fresh data..."):
                            fetch_yahoo_data(leagues_dict[selected_league_name])
                            st.success("Synced!")
                            st.rerun()
                with c_dis:
                    if st.button("Disconnect", type="tertiary", use_container_width=True):
                        del st.session_state['yahoo_token_data']
                        st.rerun()
            else:
                st.warning("No hockey leagues found.")

st.divider()

# --- GLOBAL DATA CALCULATION ---
calc_season = season_choice if 'season_choice' in locals() else "20252026"
calc_start_date = stats_start_date if stats_start_date else "2025-10-01"
calc_end_date = stats_end_date if stats_end_date else str(date.today())

s_df_global = load_skaters(calc_season, calc_start_date, calc_end_date)
g_df_global = load_goalies(calc_season, calc_start_date, calc_end_date)

# --- FIX: THE FANTASY BASELINE ---
# Filter out 4th liners to establish a realistic mathematical average
min_gp = 5 if timeframe == "Full Season" else 1

if not g_df_global.empty:
    g_df_math_pool = g_df_global[g_df_global['GP'] >= (min_gp - 2)] # Goalies play less
    evaluated_goalies = calculate_z_scores(g_df_math_pool, {'W': False, 'GAA': True, 'SV%': False, 'SHO': False})
    if 'Total Z' in evaluated_goalies.columns:
        evaluated_goalies = evaluated_goalies.rename(columns={'Total Z': 'NexusScore'})
    evaluated_goalies['match_key'] = evaluated_goalies['Player'].str.lower().str.strip()
else:
    evaluated_goalies = pd.DataFrame()

if not s_df_global.empty:
    s_df_math_pool = s_df_global[s_df_global['GP'] >= min_gp]
    evaluated_df = calculate_z_scores(s_df_math_pool, weights)
    
    if 'Total Z' in evaluated_df.columns:
        evaluated_df = evaluated_df.rename(columns={'Total Z': 'NexusScore'})
        evaluated_df['match_key'] = evaluated_df['Player'].str.lower().str.strip()
        
        # FIX: Ensure playerId survives the math engine so images can render
        if 'playerId' not in evaluated_df.columns and 'playerId' in s_df_global.columns:
            evaluated_df = pd.merge(evaluated_df, s_df_global[['Player', 'playerId']].drop_duplicates(), on='Player', how='left')
    else:
        st.error("Error: 'Total Z' column not generated. Check monster_math.py.")
        st.stop()
else:
    evaluated_df = pd.DataFrame()

# Safety stop for the UI
if evaluated_df.empty:
    st.error("No skater data available. Please check your NHL API connection.")
    st.stop()

# --- UI LAYOUT ---
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
    "📊 DASHBOARD", "📅 SCHEDULE", "⚖️ WAR ROOM", 
    "🥅 GOALIES", "📈 TRENDS", "🦅 WIRE HAWK", 
    "🏆 POWER RANKINGS", "⚔️ MATCHUP", "🔮 PLAYOFF PRIMER"
])

# =========================================
# TAB 1: DASHBOARD (Positional Scarcity Edition)
# =========================================
with tab1:
    final = evaluated_df.copy()
    
    if not final.empty:
        baselines = {}
        for pos in ['C', 'L', 'R', 'D']:
            pos_players = final[final['Pos'].str.contains(pos, na=False)].sort_values('NexusScore', ascending=False)
            baselines[pos] = pos_players.head(12)['NexusScore'].mean() if len(pos_players) > 0 else 0
        
        def calculate_vorp(row):
            if pd.isna(row['Pos']): return 0.0
            primary_pos = str(row['Pos']).replace('/', ',').split(',')[0].strip()
            if primary_pos in baselines:
                return row['NexusScore'] - baselines[primary_pos]
            return 0.0

        final['VORP'] = final.apply(calculate_vorp, axis=1)

        st.markdown("### 🎯 Player Value Dashboard")
        st.caption("Players are sorted by their **NexusScore** (overall mathematical value). The **Scarcity** column reveals their true positional value.")

        col_f, col_s = st.columns([3, 1])
        with col_f:
            selected_pos = st.multiselect("Filter Position", ['C', 'L', 'R', 'D'], default=['C', 'L', 'R', 'D'], key="dash_pos")
        
        final = final[final['Pos'].isin(selected_pos)] if 'Pos' in final.columns else final
        final = final.sort_values(by="NexusScore", ascending=False)
        
        # Safe Image Generation
        if 'Team' in final.columns: final['Logo'] = final['Team'].apply(get_team_logo)
        if 'playerId' in final.columns: final['Headshot'] = final.apply(get_headshot, axis=1)

        # EXACT REQUESTED ORDER
        cols_order = ['Headshot', 'Logo', 'Team', 'Player', 'Pos', 'NexusScore', 'VORP', 'GP'] + cats
        actual_cols = [c for c in cols_order if c in final.columns]
        
        # Removed VORP from heatmap to reduce red overload
        heatmap_cols = ['NexusScore'] + [c for c in cats if c in final.columns]

        st.dataframe(
            final[actual_cols].style.format("{:.2f}", subset=['VORP', 'NexusScore'])
                 .background_gradient(cmap="RdYlGn", subset=heatmap_cols),
            height=800, 
            column_config={
                "Headshot": st.column_config.ImageColumn("", width="small"),
                "Logo": st.column_config.ImageColumn("", width="small"),
                "Team": st.column_config.TextColumn("Team", width="small"),
                "Player": st.column_config.TextColumn("Player", width="medium"),
                "Pos": st.column_config.TextColumn("Pos", width="small"),
                "NexusScore": st.column_config.NumberColumn("NexusScore", format="%.2f", width="small"),
                "VORP": st.column_config.NumberColumn("Scarcity", format="%.2f", width="small"),
                "GP": st.column_config.NumberColumn("GP", width="small")
            },
            hide_index=True, 
            use_container_width=True 
        )
    else:
        st.error("No skater data found in global calculation.")

# =========================================
# TAB 2: SCHEDULE
# =========================================
with tab2:
    st.header("📅 Weekly Schedule & Off-Nights")
    st.caption("Maximize your games played by targeting teams playing on light nights (Off-Nights: Mon, Wed, Fri, Sun).")
    
    try:
        today_date = date.today()
        weeks = get_fantasy_weeks()
        current_week = next((w for w in weeks if w['start'] <= today_date <= w['end']), weeks[0])
        
        start_str = str(current_week['start'])
        end_str = str(current_week['end'])
        
        st.markdown(f"**Current Fantasy Week:** `{start_str}` to `{end_str}`")
        
        week_sched = get_nhl_schedule(start_str)
        if week_sched:
            sched_data = []
            for d, games in week_sched.items():
                if start_str <= d <= end_str:
                    dt = datetime.strptime(d, "%Y-%m-%d")
                    is_off_night = dt.weekday() in [0, 2, 4, 6] 
                    for team, opp in games.items():
                        sched_data.append({'Team': team, 'Date': d, 'Off-Night': is_off_night})
            
            if sched_data:
                sdf = pd.DataFrame(sched_data)
                team_summary = sdf.groupby('Team').agg(
                    Total_Games=('Date', 'count'),
                    Off_Nights=('Off-Night', 'sum')
                ).reset_index().sort_values(by=['Off_Nights', 'Total_Games'], ascending=[False, False])
                
                team_summary['Logo'] = team_summary['Team'].apply(get_team_logo)
                
                st.dataframe(
                    team_summary[['Logo', 'Team', 'Total_Games', 'Off_Nights']].style.background_gradient(cmap="Purples", subset=['Off_Nights']),
                    column_config={"Logo": st.column_config.ImageColumn("Team", width="small")},
                    hide_index=True, use_container_width=True
                )
    except Exception as e:
        st.warning(f"Could not load schedule: {e}")

# =========================================
# TAB 2: SCHEDULE
# =========================================
with tab2:
    st.header("📅 Weekly Schedule & Off-Nights")
    st.caption("Maximize your games played by targeting teams playing on light nights (Off-Nights: Mon, Wed, Fri, Sun).")
    
    try:
        today_date = date.today()
        weeks = get_fantasy_weeks()
        current_week = next((w for w in weeks if w['start'] <= today_date <= w['end']), weeks[0])
        
        start_str = str(current_week['start'])
        end_str = str(current_week['end'])
        
        st.markdown(f"**Current Fantasy Week:** `{start_str}` to `{end_str}`")
        
        week_sched = get_nhl_schedule(start_str)
        if week_sched:
            sched_data = []
            for d, games in week_sched.items():
                if start_str <= d <= end_str:
                    dt = datetime.strptime(d, "%Y-%m-%d")
                    is_off_night = dt.weekday() in [0, 2, 4, 6] 
                    for team, opp in games.items():
                        sched_data.append({'Team': team, 'Date': d, 'Off-Night': is_off_night})
            
            if sched_data:
                sdf = pd.DataFrame(sched_data)
                team_summary = sdf.groupby('Team').agg(
                    Total_Games=('Date', 'count'),
                    Off_Nights=('Off-Night', 'sum')
                ).reset_index().sort_values(by=['Off_Nights', 'Total_Games'], ascending=[False, False])
                
                team_summary['Logo'] = team_summary['Team'].apply(get_team_logo)
                
                st.dataframe(
                    team_summary[['Logo', 'Team', 'Total_Games', 'Off_Nights']].style.background_gradient(cmap="Purples", subset=['Off_Nights']),
                    column_config={"Logo": st.column_config.ImageColumn("Team", width="small")},
                    hide_index=True, use_container_width=True
                )
    except Exception as e:
        st.warning(f"Could not load schedule: {e}")

# =========================================
# TAB 3: WAR ROOM (Blockbuster Edition)
# =========================================
with tab3:
    st.header("⚖️ WAR ROOM: Blockbuster Trade Machine")
    if not final.empty:
        c1, c2 = st.columns(2)
        with c1: 
            p1_list = st.multiselect("Team A Gives (You)", final['Player'].unique(), key="t1_select")
        with c2: 
            p2_list = st.multiselect("Team B Gives (Them)", final['Player'].unique(), key="t2_select")

        if p1_list and p2_list:
            p1_data = final[final['Player'].isin(p1_list)]
            p2_data = final[final['Player'].isin(p2_list)]
            
            p1_total = p1_data['NexusScore'].sum()
            p2_total = p2_data['NexusScore'].sum()
            
            col_p1, col_vs, col_p2 = st.columns([2, 1, 2])
            
            with col_p1:
                st.markdown("<h3 style='text-align: center; color: #FF4B4B;'>Team A Package</h3>", unsafe_allow_html=True)
                for _, row in p1_data.iterrows():
                    st.markdown(f"**{row['Player']}** ({row['Pos']}): {row['NexusScore']:.2f} Nexus")
                st.metric("Total Package Value", f"{p1_total:.2f}")

            with col_vs: 
                st.markdown("<h1 style='text-align: center; padding-top: 50px; font-size: 60px;'>VS</h1>", unsafe_allow_html=True)

            with col_p2:
                st.markdown("<h3 style='text-align: center; color: #00CC96;'>Team B Package</h3>", unsafe_allow_html=True)
                for _, row in p2_data.iterrows():
                    st.markdown(f"**{row['Player']}** ({row['Pos']}): {row['NexusScore']:.2f} Nexus")
                st.metric("Total Package Value", f"{p2_total:.2f}", delta=f"{(p2_total - p1_total):.2f}")

            st.divider()

            if len(p1_list) != len(p2_list):
                st.warning(f"⚠️ **Uneven Trade Detected:** This is a {len(p1_list)}-for-{len(p2_list)} swap. The side receiving fewer players gains an empty roster spot, which holds the value of a top Free Agent (often ~1.5 to 2.0 Nexus on the wire).")
            
            diff = p2_total - p1_total
            if diff > 1.0: verdict, v_color = "🔥 ACCEPT: Clear Upgrade", "#00CC96"
            elif diff < -1.0: verdict, v_color = "❌ DECLINE: Massive Value Loss", "#FF4B4B"
            else: verdict, v_color = "⚖️ NEUTRAL: Fair Swap or Needs Context", "#FF914D"

            st.markdown(f"""
                <div style="background-color: #1c1f26; padding: 20px; border-radius: 10px; border-left: 5px solid {v_color};">
                    <h2 style="margin:0;">VERDICT: {verdict}</h2>
                    <p style="margin-top:10px;">Net Value Change: <b>{diff:+.2f} Nexus</b></p>
                </div>
            """, unsafe_allow_html=True)

            st.divider()
            st.subheader("📅 Weekly Package Outlook")
            
            today_date = date.today()
            weeks = get_fantasy_weeks()
            current_week = next((w for w in weeks if w['start'] <= today_date <= w['end']), weeks[0])
            
            start_str = str(current_week['start'])
            end_str = str(current_week['end'])
            week_sched = get_nhl_schedule(start_str)
            
            def count_games(team_abbr, schedule_dict):
                if not schedule_dict: return 0
                count = 0
                for day, games in schedule_dict.items():
                    if start_str <= day <= end_str:
                        if team_abbr in games: count += 1
                return count

            p1_games = sum(count_games(row['Team'], week_sched) for _, row in p1_data.iterrows())
            p2_games = sum(count_games(row['Team'], week_sched) for _, row in p2_data.iterrows())
            
            p1_proj = sum(row['NexusScore'] * count_games(row['Team'], week_sched) for _, row in p1_data.iterrows())
            p2_proj = sum(row['NexusScore'] * count_games(row['Team'], week_sched) for _, row in p2_data.iterrows())

            col_m1, col_m2 = st.columns(2)
            with col_m1:
                st.metric(f"Team A ({p1_games} total games)", f"{p1_proj:.2f} Nexus")
            with col_m2:
                st.metric(f"Team B ({p2_games} total games)", f"{p2_proj:.2f} Nexus", delta=f"{(p2_proj - p1_proj):.2f}")
                
            st.caption(f"Projected for Fantasy Week: {start_str} to {end_str}")

        else:
            st.info("Select at least one player for both teams to analyze the blockbuster.")

        st.divider()
        st.header("🚦 DAILY START / SIT OPTIMIZER")
        st.caption("Select players fighting for your final active roster spots tonight. We will check the NHL schedule and rank them by mathematical value.")
        
        bench_mob = st.multiselect("Select Players to Compare", final['Player'].unique(), key="bench_select")
        
        if bench_mob:
            today_str = str(date.today())
            daily_sched = get_nhl_schedule(today_str)
            todays_games = daily_sched.get(today_str, {}) if daily_sched else {}
            
            bench_data = final[final['Player'].isin(bench_mob)].copy()
            bench_data['Plays Tonight'] = bench_data['Team'].apply(lambda t: "Yes" if t in todays_games else "No")
            bench_data['Opponent'] = bench_data['Team'].apply(lambda t: todays_games.get(t, "N/A"))
            
            sort_col = 'VORP' if 'VORP' in bench_data.columns else 'NexusScore'
            bench_data = bench_data.sort_values(by=['Plays Tonight', sort_col], ascending=[False, False])
            
            st.markdown("### 🎯 Optimizer Recommendation")
            
            active_players = bench_data[bench_data['Plays Tonight'] == 'Yes']
            if not active_players.empty:
                top_start = active_players.iloc[0]
                st.success(f"**START:** {top_start['Player']} vs {top_start['Opponent']} (Value: {top_start[sort_col]:.2f})")
                
                st.dataframe(
                    bench_data[['Headshot', 'Player', 'Team', 'Plays Tonight', 'Opponent', sort_col]],
                    column_config={"Headshot": st.column_config.ImageColumn("Img", width="small")},
                    hide_index=True, use_container_width=True
                )
            else:
                st.warning("None of the selected players have a game scheduled for tonight!")

    else:
        st.warning("No data available for player comparison.")

# =========================================
# TAB 4: GOALIES
# =========================================
with tab4:
    # Pass the end date here to make sure custom calendar ranges work for goalies too
    g_df = load_goalies(calc_season, calc_start_date, calc_end_date)
    
    if not g_df.empty:
        r_g = calculate_z_scores(g_df, {'W': False, 'GAA': True, 'SV%': False, 'SHO': False})
        
        if 'Team' in r_g.columns: r_g['Logo'] = r_g['Team'].apply(get_team_logo)
        if 'playerId' in r_g.columns: r_g['Headshot'] = r_g.apply(get_headshot, axis=1)
        
        # Rebrand to NexusScore
        if 'Total Z' in r_g.columns: 
            r_g = r_g.rename(columns={'Total Z': 'NexusScore'})
            
        # Safely check which columns actually exist before trying to display them
        cols_order = ['Headshot', 'Logo', 'Player', 'Team', 'NexusScore', 'GP', 'W', 'GAA', 'SV%', 'SHO']
        actual_cols = [c for c in cols_order if c in r_g.columns]
        
        g_heatmap = ['NexusScore', 'W', 'GAA', 'SV%', 'SHO']
        actual_heatmap = [c for c in g_heatmap if c in r_g.columns]
        
        st.dataframe(
            r_g[actual_cols].style.format({
                "NexusScore": "{:.2f}", "W": "{:.0f}", "GAA": "{:.3f}", 
                "SV%": "{:.3f}", "SHO": "{:.0f}", "GP": "{:.0f}"
            }).background_gradient(cmap="RdYlGn", subset=actual_heatmap),
            column_config={
                "Headshot": st.column_config.ImageColumn("Img", width="small"),
                "Logo": st.column_config.ImageColumn("Team", width="small"),
                "NexusScore": st.column_config.NumberColumn("NexusScore", format="%.2f")
            },
            height=600, use_container_width=True, hide_index=True 
        )
    else:
        st.warning("No goalie data found.")

# =========================================
# TAB 5: TRENDS
# =========================================
with tab5:
    if st.button("🚀 Run Trends"):
        with st.spinner("Crunching..."):
            df_s = get_nhl_skater_stats(calc_season, None)
            df_r = get_nhl_skater_stats(calc_season, str(date.today() - timedelta(days=30)))

            if not df_s.empty and not df_r.empty:
                numeric_cols = ['G', 'A', 'SOG', 'HIT', 'BLK', 'PIM', 'PPP', '+/-']
                for d in [df_s, df_r]:
                    for c in numeric_cols: 
                        if c in d.columns: d[c] = pd.to_numeric(d[c], errors='coerce').fillna(0)
                
                current_pos = selected_pos if 'selected_pos' in locals() else ['C', 'L', 'R', 'D']
                df_s = df_s[df_s['Pos'].isin(current_pos)]; df_r = df_r[df_r['Pos'].isin(current_pos)]
                
                z_s = calculate_z_scores(df_s, cats); z_r = calculate_z_scores(df_r, cats)
                z_s['S_Val'] = sum(z_s.get(f"{c}V", 0) * weights[c] for c in cats)
                z_r['R_Val'] = sum(z_r.get(f"{c}V", 0) * weights[c] for c in cats)
                
                trend = pd.merge(z_s[['playerId', 'Player', 'Team', 'S_Val']], z_r[['playerId', 'R_Val']], on='playerId')
                trend['Trend'] = trend['R_Val'] - trend['S_Val']
                trend['Logo'] = trend['Team'].apply(get_team_logo); trend['Headshot'] = trend.apply(get_headshot, axis=1)
                
                cols = ['Headshot', 'Logo', 'Player', 'Trend', 'S_Val', 'R_Val']
                c1, c2 = st.columns(2)
                with c1: 
                    st.subheader("🔥 Heating Up")
                    st.dataframe(
                        trend.sort_values('Trend', ascending=False).head(20)[cols].style.format("{:.2f}", subset=['Trend', 'S_Val', 'R_Val']).background_gradient(cmap="Greens", subset=['Trend']),
                        column_config={"Logo": st.column_config.ImageColumn("Team", width="small"), "Headshot": st.column_config.ImageColumn("Img", width="small")},
                        hide_index=True, use_container_width=True
                    )
                with c2: 
                    st.subheader("❄️ Cooling Down")
                    st.dataframe(
                        trend.sort_values('Trend', ascending=True).head(20)[cols].style.format("{:.2f}", subset=['Trend', 'S_Val', 'R_Val']).background_gradient(cmap="Reds_r", subset=['Trend']),
                        column_config={"Logo": st.column_config.ImageColumn("Team", width="small"), "Headshot": st.column_config.ImageColumn("Img", width="small")},
                        hide_index=True, use_container_width=True
                    )

# =========================================
# TAB 6: WIRE HAWK (Advanced Scout & FAs)
# =========================================
with tab6:
    st.subheader("🦅 THE WIRE HAWK")
    st.caption("Cross-references your synced Yahoo league against the global PuckNexus calculation engine. Use the Control Center above to sync your league.")
    
    target_file = "yahoo_export.csv" 
    
    if 'final' in locals() and not final.empty:
        try:
            y_data = pd.read_csv(target_file)
            final['match_key'] = final['Player'].str.lower().str.strip()
            y_data['match_key'] = y_data['name'].str.lower().str.strip()
            
            merged = pd.merge(y_data, final, left_on='match_key', right_on='match_key', how='inner')
            merged = merged.drop_duplicates(subset=['match_key'])
            
            if 'Team' in merged.columns: merged['Logo'] = merged['Team'].apply(get_team_logo)
            if 'playerId' in merged.columns: merged['Headshot'] = merged.apply(get_headshot, axis=1)

            fa = merged[merged['Status'] == 'Free Agent'].sort_values('NexusScore', ascending=False)
            
            if 'Is_Mine' in merged.columns:
                ros = merged[merged['Is_Mine'] == True].sort_values('NexusScore', ascending=False)
            else:
                st.warning("Old export detected. Please run a fresh Sync to detect your specific team.")
                ros = merged[merged['Status'] == 'Rostered'].sort_values('NexusScore', ascending=False)

            # Schedule logic
            today_date = date.today()
            today_str = str(today_date)
            weeks = get_fantasy_weeks()
            current_week = next((w for w in weeks if w['start'] <= today_date <= w['end']), weeks[0])
            end_str = str(current_week['end'])
            
            rem_sched = get_nhl_schedule(today_str)
            team_rem_games = {}
            team_rem_off = {}
            
            if rem_sched:
                for d, games in rem_sched.items():
                    if today_str <= d <= end_str:
                        dt = datetime.strptime(d, "%Y-%m-%d")
                        is_off_night = dt.weekday() in [0, 2, 4, 6] 
                        for team, opp in games.items():
                            team_rem_games[team] = team_rem_games.get(team, 0) + 1
                            if is_off_night:
                                team_rem_off[team] = team_rem_off.get(team, 0) + 1

            fa['Rem G'] = fa['Team'].map(team_rem_games).fillna(0).astype(int)
            fa['Off-Nights'] = fa['Team'].map(team_rem_off).fillna(0).astype(int)
            
            # --- THE ADVANCED SCOUT ---
            if not ros.empty and not fa.empty:
                active_cats = [c for c in cats if weights[c] > 0]
                if active_cats:
                    team_analysis = ros[[f"{c}V" for c in active_cats]].mean()
                    weakest_cat_v = team_analysis.idxmin()
                    weakest_cat = weakest_cat_v.replace('V', '')
                    
                    playable_fa = fa[fa['Rem G'] > 0]
                    if not playable_fa.empty:
                        best_fa = playable_fa.sort_values(by=[weakest_cat_v, 'Off-Nights'], ascending=[False, False]).iloc[0]
                        
                        st.markdown(f"""
                            <div style="background-color: #1c1f26; padding: 15px; border-radius: 10px; border-left: 5px solid #FF914D; margin-bottom: 20px;">
                                <h3 style="margin:0; color: #FF914D;">🦅 ADVANCED SCOUT'S RECOMMENDATION</h3>
                                <p style="margin:10px 0 0 0;">Team Weakness: <b>{weakest_cat}</b> (Avg: {team_analysis[weakest_cat_v]:.2f}).<br>
                                Top FA Target: <b>{best_fa['name']}</b> ({best_fa[weakest_cat_v]:.2f} Category Score).<br>
                                <i style="color: #00CC96;">Schedule Edge: {best_fa['Rem G']} games remaining this week, including <b>{best_fa['Off-Nights']} off-nights</b>.</i></p>
                            </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.info("No free agents have games remaining this week.")
            
            st.divider()
            
            heatmap_subset = ['NexusScore'] + cats
            
            st.subheader("📋 My Roster")
            ros_cols = ['Headshot', 'Logo', 'name', 'Team', 'Pos', 'NexusScore'] + cats
            st.dataframe(
                ros[ros_cols].style.format("{:.2f}", subset=['NexusScore'])
                             .background_gradient(cmap="RdYlGn", subset=heatmap_subset), 
                column_config={
                    "Logo": st.column_config.ImageColumn("Team", width="small"), 
                    "Headshot": st.column_config.ImageColumn("Img", width="small"),
                    "NexusScore": st.column_config.NumberColumn("NexusScore", format="%.2f")
                }, 
                hide_index=True, 
                use_container_width=True
            )
            
            st.divider()
            
            st.subheader("💎 Free Agents")
            fa_cols = ['Headshot', 'Logo', 'name', 'Team', 'Pos', 'Rem G', 'Off-Nights', 'NexusScore'] + cats
            st.dataframe(
                fa[fa_cols].style.format("{:.2f}", subset=['NexusScore'])
                           .background_gradient(cmap="RdYlGn", subset=heatmap_subset), 
                column_config={
                    "Logo": st.column_config.ImageColumn("Team", width="small"), 
                    "Headshot": st.column_config.ImageColumn("Img", width="small"),
                    "NexusScore": st.column_config.NumberColumn("NexusScore", format="%.2f")
                }, 
                hide_index=True, 
                use_container_width=True
            )
        except Exception as e: 
            st.info(f"Run 'Sync with Yahoo' to load data. System message: {e}")

# =========================================
# TAB 7: LEAGUE POWER RANKINGS
# =========================================
with tab7:
    st.header("🏆 League Power Rankings")
    try:
        yahoo_df = pd.read_csv("yahoo_export.csv")
        
        active_cats = [c for c in cats if weights[c] > 0]
        s_cat_cols = [f"{c}V" for c in active_cats]
        g_cat_cols = ['WV', 'GAAV', 'SV%V', 'SHOV']
        
        s_cols = ['match_key', 'NexusScore'] + [c for c in s_cat_cols if c in evaluated_df.columns]
        g_cols = ['match_key', 'NexusScore'] + [c for c in g_cat_cols if c in evaluated_goalies.columns]
        
        skater_league = pd.merge(yahoo_df, evaluated_df[s_cols], on='match_key', how='inner')
        goalie_league = pd.merge(yahoo_df, evaluated_goalies[g_cols], on='match_key', how='inner')
        
        full_league_df = pd.concat([skater_league, goalie_league]).fillna(0)
        rostered_df = full_league_df[full_league_df['Status'] == 'Rostered']
        
        all_cat_cols = [c for c in s_cat_cols + g_cat_cols if c in rostered_df.columns]
        team_power = rostered_df.groupby(['Fantasy_Team', 'Manager'])[['NexusScore'] + all_cat_cols].sum().reset_index()
        team_power = team_power.sort_values(by='NexusScore', ascending=True) 
        
        st.subheader("⚡ True Team Power (Skaters + Goalies)")
        fig1 = px.bar(team_power, x='NexusScore', y='Fantasy_Team', orientation='h', 
                     color='NexusScore', color_continuous_scale='viridis', text_auto='.2f')
        fig1.update_layout(height=400, showlegend=False)
        st.plotly_chart(fig1, use_container_width=True)
        
        st.divider()
        
        st.subheader("🧬 Category Dominance Breakdown")
        st.caption("Hover over the segments to see exactly where teams are gaining or losing value.")
        fig2 = px.bar(team_power, x=all_cat_cols, y='Fantasy_Team', orientation='h',
                     labels={'value': 'Total NexusScore', 'variable': 'Category'})
        
        fig2.update_layout(height=600, barmode='relative', legend_title_text='Categories')
        st.plotly_chart(fig2, use_container_width=True)
        
    except FileNotFoundError:
        st.warning("⚠️ yahoo_export.csv not found. Run 'Sync with Yahoo' in the Control Center.")

# =========================================
# TAB 7: LEAGUE POWER RANKINGS
# =========================================
with tab7:
    st.header("🏆 League Power Rankings")
    try:
        yahoo_df = pd.read_csv("yahoo_export.csv")
        
        # 1. Define Category Columns to Pull (based on your active sidebar weights)
        active_cats = [c for c in cats if weights[c] > 0]
        s_cat_cols = [f"{c}V" for c in active_cats]
        g_cat_cols = ['WV', 'GAAV', 'SV%V', 'SHOV']
        
        # Safely only grab columns that actually generated
        s_cols = ['match_key', 'Total Z'] + [c for c in s_cat_cols if c in evaluated_df.columns]
        g_cols = ['match_key', 'Total Z'] + [c for c in g_cat_cols if c in evaluated_goalies.columns]
        
        # 2. Merge Skaters & Goalies with Yahoo Data
        skater_league = pd.merge(yahoo_df, evaluated_df[s_cols], on='match_key', how='inner')
        goalie_league = pd.merge(yahoo_df, evaluated_goalies[g_cols], on='match_key', how='inner')
        
        # 3. Combine & Clean (Fill missing cats with 0, e.g., skaters have 0 GAA)
        full_league_df = pd.concat([skater_league, goalie_league]).fillna(0)
        rostered_df = full_league_df[full_league_df['Status'] == 'Rostered']
        
        # 4. Group by Team and Sum everything
        all_cat_cols = [c for c in s_cat_cols + g_cat_cols if c in rostered_df.columns]
        team_power = rostered_df.groupby(['Fantasy_Team', 'Manager'])[['Total Z'] + all_cat_cols].sum().reset_index()
        team_power = team_power.sort_values(by='Total Z', ascending=True) 
        
        # 5. Visualization 1: Overall True Power
        st.subheader("⚡ True Team Power (Skaters + Goalies)")
        fig1 = px.bar(team_power, x='Total Z', y='Fantasy_Team', orientation='h', 
                     color='Total Z', color_continuous_scale='viridis', text_auto='.2f')
        fig1.update_layout(height=400, showlegend=False)
        st.plotly_chart(fig1, use_container_width=True)
        
        st.divider()
        
        # 6. Visualization 2: Category Dominance (The New Chart)
        st.subheader("🧬 Category Dominance Breakdown")
        st.caption("Hover over the segments to see exactly where teams are gaining or losing value.")
        fig2 = px.bar(team_power, x=all_cat_cols, y='Fantasy_Team', orientation='h',
                     labels={'value': 'Total Z-Score', 'variable': 'Category'})
        
        # 'relative' barmode stacks positive values on the right, negatives on the left
        fig2.update_layout(height=600, barmode='relative', legend_title_text='Categories')
        st.plotly_chart(fig2, use_container_width=True)
        
    except FileNotFoundError:
        st.warning("⚠️ yahoo_export.csv not found. Run 'Sync with Yahoo' in the Wire Hawk tab.")

# =========================================
# TAB 8: H2H MATCHUP SIMULATOR (Live Data Edition)
# =========================================
with tab8:
    st.header("⚔️ H2H Matchup Simulator")
    try:
        target_file = "yahoo_export.csv"
        yahoo_df = pd.read_csv(target_file)
        yahoo_df['match_key'] = yahoo_df['name'].str.lower().str.strip()

        # Identify "My Team" to auto-select it in the dropdown
        my_team_name = yahoo_df[yahoo_df['Is_Mine'] == True]['Fantasy_Team'].iloc[0] if 'Is_Mine' in yahoo_df.columns and not yahoo_df[yahoo_df['Is_Mine'] == True].empty else None
        
        teams = sorted(yahoo_df['Fantasy_Team'].dropna().unique())
        
        if len(teams) >= 2:
            col1, col2 = st.columns(2)
            
            default_idx_a = teams.index(my_team_name) if my_team_name in teams else 0
            default_idx_b = 1 if default_idx_a == 0 else 0
            
            with col1: team_a = st.selectbox("Team A", teams, index=default_idx_a)
            with col2: team_b = st.selectbox("Team B", teams, index=default_idx_b)

            if st.button("🔮 Run Live Matchup Engine", use_container_width=True):
                with st.spinner(f"Crunching live weekly stats and simulating remaining schedule based on {timeframe} trends..."):
                    # --- 1. TIMEFRAME & SPLIT LOGIC ---
                    today_date = date.today()
                    # Current stats pull up to yesterday. Remaining projections start today.
                    yesterday_str = str(today_date - timedelta(days=1))
                    today_str = str(today_date)
                    
                    weeks = get_fantasy_weeks()
                    current_week = next((w for w in weeks if w['start'] <= today_date <= w['end']), weeks[0])
                    start_str = str(current_week['start'])
                    end_str = str(current_week['end'])
                    
                    active_cats = [c for c in cats if weights[c] > 0]
                    
                    # --- 2. CURRENT STATS (Start of week to Yesterday) ---
                    cw_df = load_skaters(calc_season, start_date=start_str, end_date=yesterday_str)
                    if not cw_df.empty:
                        cw_df['match_key'] = cw_df['Player'].str.lower().str.strip()
                    else:
                        cw_df = pd.DataFrame(columns=['match_key'] + active_cats)
                        
                    # --- 3. PROJECTED PER-GAME STATS (Based on Global Timeframe) ---
                    proj_df = s_df_global.copy()
                    proj_df['match_key'] = proj_df['Player'].str.lower().str.strip()
                    
                    for c in active_cats:
                        if c in proj_df.columns:
                            proj_df[c] = pd.to_numeric(proj_df[c], errors='coerce').fillna(0)
                            proj_df[f"{c}_pg"] = proj_df[c] / proj_df['GP'].clip(lower=1) # Avoid div by zero
                        else:
                            proj_df[f"{c}_pg"] = 0.0

                    # --- 4. REMAINING SCHEDULE (Today to End of Week) ---
                    rem_sched = get_nhl_schedule(today_str) 
                    def get_rem_games(nhl_team):
                        if not rem_sched: return 0
                        count = 0
                        for day, games in rem_sched.items():
                            if today_str <= day <= end_str:
                                if nhl_team in games: count += 1
                        return count
                        
                    proj_df['Rem_G'] = proj_df['Team'].apply(get_rem_games)

                    # --- 5. ROSTER SPLITS ---
                    roster_a = yahoo_df[(yahoo_df['Fantasy_Team'] == team_a) & (yahoo_df['Status'] == 'Rostered')]
                    roster_b = yahoo_df[(yahoo_df['Fantasy_Team'] == team_b) & (yahoo_df['Status'] == 'Rostered')]

                    # --- 6. CALCULATE TOTALS ---
                    team_a_cw = pd.merge(roster_a, cw_df, on='match_key', how='inner') if not cw_df.empty else pd.DataFrame()
                    team_a_cur = {c: team_a_cw[c].sum() if c in team_a_cw.columns else 0 for c in active_cats}
                    
                    team_b_cw = pd.merge(roster_b, cw_df, on='match_key', how='inner') if not cw_df.empty else pd.DataFrame()
                    team_b_cur = {c: team_b_cw[c].sum() if c in team_b_cw.columns else 0 for c in active_cats}
                    
                    team_a_proj_df = pd.merge(roster_a, proj_df, on='match_key', how='inner')
                    team_a_rem = {c: sum(row[f"{c}_pg"] * row['Rem_G'] for _, row in team_a_proj_df.iterrows()) for c in active_cats}
                    
                    team_b_proj_df = pd.merge(roster_b, proj_df, on='match_key', how='inner')
                    team_b_rem = {c: sum(row[f"{c}_pg"] * row['Rem_G'] for _, row in team_b_proj_df.iterrows()) for c in active_cats}
                    
                    # --- 7. COMPILE DATAFRAMES FOR UI ---
                    current_data, rem_data, final_data = [], [], []
                    a_wins, b_wins, ties = 0, 0, 0
                    
                    for c in active_cats:
                        a_cur, b_cur = team_a_cur[c], team_b_cur[c]
                        a_rem, b_rem = team_a_rem[c], team_b_rem[c]
                        a_tot, b_tot = a_cur + a_rem, b_cur + b_rem
                        
                        current_data.append({'Category': c, team_a: a_cur, team_b: b_cur})
                        rem_data.append({'Category': c, team_a: a_rem, team_b: b_rem})
                        
                        # Determine winner (Standard Yahoo: Higher is better for all skater cats)
                        if a_tot > b_tot:
                            winner, a_wins = team_a, a_wins + 1
                        elif b_tot > a_tot:
                            winner, b_wins = team_b, b_wins + 1
                        else:
                            winner, ties = "Tie", ties + 1
                            
                        final_data.append({'Category': c, team_a: a_tot, team_b: b_tot, 'Winner': winner})
                        
                    # --- BUILD THE UI ---
                    st.divider()
                    
                    # Big Scoreboard Metric
                    st.markdown(f"""
                        <div style="background-color: #1c1f26; padding: 20px; border-radius: 10px; border-left: 5px solid {'#00CC96' if a_wins > b_wins else ('#FF914D' if a_wins == b_wins else '#FF4B4B')}; text-align: center; margin-bottom: 20px;">
                            <h3 style="margin:0; color: #888;">Projected Final: {team_a} vs {team_b}</h3>
                            <h1 style="margin:0; font-size: 50px;">{a_wins} - {b_wins} - {ties}</h1>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    col_cur, col_rem = st.columns(2)
                    
                    with col_cur:
                        st.subheader("🏒 Current Weekly Score")
                        st.caption(f"Actual stats accumulated from {start_str} to yesterday.")
                        df_cur = pd.DataFrame(current_data)
                        st.dataframe(
                            df_cur.style.highlight_max(subset=[team_a, team_b], color='#2e7b50', axis=1).format({team_a: "{:.0f}", team_b: "{:.0f}"}), 
                            use_container_width=True, hide_index=True
                        )
                        
                    with col_rem:
                        st.subheader("🔮 Projected Remaining")
                        st.caption(f"Expected output from today to {end_str} based on **{timeframe}** trends.")
                        df_rem = pd.DataFrame(rem_data)
                        st.dataframe(
                            df_rem.style.highlight_max(subset=[team_a, team_b], color='#2e7b50', axis=1).format({team_a: "{:.1f}", team_b: "{:.1f}"}), 
                            use_container_width=True, hide_index=True
                        )
                        
                    st.subheader("🏆 Final Projected Box Score")
                    st.caption("Current Weekly Score + Projected Remaining Output")
                    df_final = pd.DataFrame(final_data)
                    st.dataframe(
                        df_final.style.highlight_max(subset=[team_a, team_b], color='#2e7b50', axis=1).format({team_a: "{:.1f}", team_b: "{:.1f}"}), 
                        use_container_width=True, hide_index=True
                    )
        else:
            st.info("Not enough teams found in yahoo_export.csv. Ensure you have run the sync.")
    except FileNotFoundError:
        st.warning("⚠️ yahoo_export.csv not found. Run 'Sync with Yahoo' in the Control Center.")

# =========================================
# TAB 9: PLAYOFF PRIMER
# =========================================
with tab9:
    st.header("🔮 PLAYOFF PRIMER: Championship Schedule Matrix")
    st.caption("Regular season wins get you to the dance, but playoff schedules win championships. This matrix calculates total games and off-nights specifically for the standard fantasy hockey playoffs.")
    
    # 1. Define standard Yahoo Playoff Window (Approx. Weeks 22-24)
    # Note: Adjust these dates slightly if your specific league playoffs differ
    playoff_start = "2026-03-16"
    playoff_end = "2026-04-05"
    
    st.markdown(f"**Targeting Playoff Window:** `{playoff_start}` to `{playoff_end}`")
    
    if st.button("🚀 Generate Playoff Matrix"):
        with st.spinner("Calculating the championship run..."):
            p_sched = get_nhl_schedule(playoff_start)
            
            if p_sched:
                team_p_games = {}
                team_p_off = {}
                
                for d, games in p_sched.items():
                    if playoff_start <= d <= playoff_end:
                        dt = datetime.strptime(d, "%Y-%m-%d")
                        is_off_night = dt.weekday() in [0, 2, 4, 6] # Mon, Wed, Fri, Sun
                        
                        for team, opp in games.items():
                            team_p_games[team] = team_p_games.get(team, 0) + 1
                            if is_off_night:
                                team_p_off[team] = team_p_off.get(team, 0) + 1
                
                # Build the DataFrame
                playoff_df = pd.DataFrame({
                    'Team': list(team_p_games.keys()),
                    'Playoff Games': list(team_p_games.values()),
                    'Off-Nights': [team_p_off.get(t, 0) for t in team_p_games.keys()]
                })
                
                # The "Championship Score" values off-nights heavily
                playoff_df['Championship Score'] = (playoff_df['Off-Nights'] * 2) + (playoff_df['Playoff Games'] - playoff_df['Off-Nights'])
                playoff_df = playoff_df.sort_values(by=['Championship Score', 'Playoff Games'], ascending=[False, False])
                playoff_df['Logo'] = playoff_df['Team'].apply(get_team_logo)
                
                # UI Layout
                col_ranks, col_advice = st.columns([2, 1])
                
                with col_ranks:
                    st.subheader("📊 Playoff Schedule Strength")
                    st.dataframe(
                        playoff_df[['Logo', 'Team', 'Championship Score', 'Playoff Games', 'Off-Nights']].style.background_gradient(cmap="Purples", subset=['Championship Score', 'Off-Nights']),
                        column_config={
                            "Logo": st.column_config.ImageColumn("Team", width="small"),
                            "Championship Score": st.column_config.ProgressColumn("Edge", min_value=0, max_value=20, format="%d")
                        },
                        hide_index=True, use_container_width=True, height=600
                    )
                
                with col_advice:
                    st.subheader("💡 Trade Deadline Advice")
                    top_teams = playoff_df.head(3)['Team'].tolist()
                    bottom_teams = playoff_df.tail(3)['Team'].tolist()
                    
                    st.success(f"**BUY TARGETS:** Target players from **{', '.join(top_teams)}**. They have the best combination of volume and off-nights during the fantasy playoffs.")
                    st.error(f"**SELL CANDIDATES:** Consider trading away players from **{', '.join(bottom_teams)}**. Their light playoff schedule could sink your championship hopes.")
            else:
                st.warning("Could not fetch schedule data for the playoff window.")