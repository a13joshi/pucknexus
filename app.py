import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
from data_fetcher import get_nhl_skater_stats, get_nhl_goalie_stats, get_nhl_schedule, get_fantasy_weeks
from monster_math import calculate_z_scores

# --- GLOBAL CONFIG ---
st.set_page_config(page_title="PuckNexus 6.4", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    h1 { 
        font-family: 'Helvetica Neue', sans-serif;
        text-transform: uppercase;
        font-weight: 900;
        letter-spacing: 2px;
        background: -webkit-linear-gradient(45deg, #FF4B4B, #FF914D);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    h2, h3 { font-family: 'Roboto Condensed', sans-serif; text-transform: uppercase; color: #FAFAFA; }
    div[data-testid="stMetric"] { background-color: #1c1f26; padding: 20px; border-radius: 10px; border-left: 5px solid #FF4B4B; }
    .spotlight { background: linear-gradient(135deg, #1c1f26 0%, #2b303b 100%); padding: 20px; border-radius: 15px; border: 1px solid #333; margin-bottom: 20px; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { height: 45px; background-color: #1c1f26; border-radius: 5px; color: #aaa; border: 1px solid #333; }
    .stTabs [aria-selected="true"] { background-color: #FF4B4B; color: white; border-color: #FF4B4B; }
</style>
""", unsafe_allow_html=True)

st.title("PUCKNEXUS // 6.4")
st.caption("THE UNOFFICIAL FANTASY HOCKEY EXPANSION")

# --- GLOBAL SIDEBAR ---
st.sidebar.markdown("### 📡 CONTROL CENTER")
season = st.sidebar.selectbox("Season", ["20252026", "20242025"])

# Timeframe Logic
timeframe = st.sidebar.selectbox("📅 Timeframe", ["Full Season", "Last 14 Days", "Last 30 Days"])
stats_start_date = None
if timeframe == "Last 14 Days":
    stats_start_date = str(date.today() - timedelta(days=14))
elif timeframe == "Last 30 Days":
    stats_start_date = str(date.today() - timedelta(days=30))

# --- STRATEGY ENGINE ---
st.sidebar.divider()
st.sidebar.markdown("### 🧠 STRATEGY")
cats = ['G', 'A', '+/-', 'PIM', 'PPP', 'SOG', 'HIT', 'BLK']

punt_cats = st.sidebar.multiselect("🗑️ Punt Categories", options=cats)
weights = {}
for cat in cats:
    if cat in punt_cats: weights[cat] = 0.0
    else:
        is_active = st.sidebar.checkbox(f"{cat}", value=True, key=f"check_{cat}")
        weights[cat] = 1.0 if is_active else 0.0

st.sidebar.info("System Status: **ONLINE** 🟢")

# --- VISUAL HELPERS ---
def get_team_logo(team_abbr):
    if not team_abbr or pd.isna(team_abbr): return ""
    logo_map = {
        "NJD": "nj", "SJS": "sj", "TBL": "tb", "LAK": "la", 
        "UTA": "utah", "VEG": "vgk", "VGK": "vgk", "MTL": "mtl",
        "WSH": "wsh", "CGY": "cgy", "WPG": "wpg"
    }
    code = logo_map.get(str(team_abbr).upper(), str(team_abbr).lower())
    return f"https://a.espncdn.com/combiner/i?img=/i/teamlogos/nhl/500/{code}.png&h=40&w=40"

def get_headshot(row):
    try:
        pid = row.get('playerId')
        team = row.get('Team')
        if pd.isna(pid) or not pid: return "" 
        pid_str = str(int(float(pid)))
        team_str = str(team).upper()
        return f"https://assets.nhle.com/mugs/nhl/20242025/{team_str}/{pid_str}.png"
    except: return ""

# --- HELPER: AI GM LOGIC ---
def generate_trade_analysis(p1_name, p1_data, p2_name, p2_data, cats, weights):
    gains, losses = [], [] 
    for c in cats:
        if weights[c] == 0: continue 
        diff = p2_data[f"{c}V"] - p1_data[f"{c}V"]
        if diff > 0.5: gains.append(c)
        elif diff < -0.5: losses.append(c)
            
    summary = ""
    if not gains and not losses: summary += "😐 **Lateral Move:** Statistically similar."
    else:
        if gains: summary += f"✅ **Gain:** **{', '.join(gains)}**.\n"
        if losses: summary += f"⚠️ **Lose:** **{', '.join(losses)}**.\n"
    val_diff = p2_data['Total Value'] - p1_data['Total Value']
    
    verdict = ""
    if val_diff > 1.0: verdict = "🔥 SMASH ACCEPT"
    elif val_diff > 0: verdict = "👍 SLIGHT WIN"
    elif val_diff > -1.0: verdict = "🤔 SLIGHT LOSS"
    else: verdict = "🛑 REJECT"
    
    return summary, verdict

# --- TABS ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 DASHBOARD", "📅 SCHEDULE", "⚖️ WAR ROOM", "🥅 GOALIES", "📈 TRENDS", "🦅 WIRE HAWK"])

@st.cache_data
def load_skaters(s, start_d): return get_nhl_skater_stats(s, start_d)

# =========================================
# TAB 1: DASHBOARD
# =========================================
with tab1:
    with st.spinner('Scouting skaters...'):
        df = load_skaters(season, stats_start_date)
        if df is not None: df = df.copy()

    if not df.empty:
        df.columns = df.columns.str.strip()
        numeric_cols = ['GP', 'G', 'A', 'PTS', '+/-', 'PIM', 'PPP', 'SOG', 'HIT', 'BLK']
        for col in numeric_cols:
            if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

        col_filter, col_spacer = st.columns([3, 1])
        with col_filter: 
            selected_pos = st.multiselect("Filter Position", ['C', 'L', 'R', 'D'], default=['C', 'L', 'R', 'D'])

        df = df[df['Pos'].isin(selected_pos)] if 'Pos' in df.columns else df
        ranked = calculate_z_scores(df, cats)
        ranked['Total Value'] = sum(ranked.get(f"{c}V", 0) * weights[c] for c in cats)
        final = ranked.sort_values(by="Total Value", ascending=False)
        
        if 'Team' in final.columns: final['Logo'] = final['Team'].apply(get_team_logo)
        if 'playerId' in final.columns: final['Headshot'] = final.apply(get_headshot, axis=1)

        # SPOTLIGHT CARD
        #top_player = final.iloc[0]
        #st.markdown('<div class="spotlight">', unsafe_allow_html=True)
        #col_img, col_stats, col_rank = st.columns([1, 2, 1])
        #with col_img:
        #    st.image(top_player['Headshot'] if top_player['Headshot'] else "https://assets.nhle.com/mugs/nhl/default-skater.png", width=180)
        #with col_stats:
        #    st.markdown(f"## {top_player['Player']}")
        #    st.markdown(f"#### {top_player['Team']} | {top_player['Pos']}")
        #    m1, m2, m3 = st.columns(3)
        #    m1.metric("Goals", top_player['G'])
        #    m2.metric("Assists", top_player['A'])
        #    m3.metric("Shots", top_player['SOG'])
        #with col_rank:
        #    st.metric("PuckNexus Rank", "#1", f"{top_player['Total Value']:.2f} Z")
        #st.markdown('</div>', unsafe_allow_html=True)

        # LEADERBOARD (HEATMAP)
        cols_order = ['Headshot', 'Logo', 'Player', 'Team', 'Pos', 'GP', 'Total Value'] + cats
        actual_cols = [c for c in cols_order if c in final.columns]
        
        # 🟢 Define columns to receive the "Green/Red" shading
        heatmap_cols = ['Total Value'] + [c for c in cats if c in final.columns]

        st.dataframe(
            final[actual_cols].style.format("{:.2f}", subset=['Total Value'])
                 .background_gradient(cmap="RdYlGn", subset=heatmap_cols), # 🟢 Applies to ALL stats now
            height=800, 
            column_config={
                "Headshot": st.column_config.ImageColumn("Img", width="small"),
                "Logo": st.column_config.ImageColumn("Team", width="small"),
                "Total Value": st.column_config.ProgressColumn("Value Rating", format="%.2f", min_value=-3, max_value=12),
            },
            hide_index=True, 
            width="stretch" # 🟢 Fixed Warning
        )
    else: st.error("No skater data found.")

# =========================================
# TAB 2: SMART SCHEDULE
# =========================================
with tab2:
    sched_data = get_nhl_schedule(str(date.today()))
    if sched_data:
        all_teams = set(); dates = sorted(sched_data.keys()); matrix = {} 
        off_night_dates = [d for d in dates if datetime.strptime(d, "%Y-%m-%d").weekday() in [0, 2, 4, 6]]

        for d in dates:
            for team, opp in sched_data[d].items():
                all_teams.add(team); 
                if team not in matrix: matrix[team] = {}
                matrix[team][d] = opp

        sched_df = pd.DataFrame.from_dict(matrix, orient='index')
        sched_df = sched_df.reindex(index=list(all_teams), columns=dates).fillna("")
        
        sched_df['Total'] = sched_df.apply(lambda x: x[x != ""].count(), axis=1)
        valid_off = [d for d in off_night_dates if d in sched_df.columns]
        sched_df['Off-Nights'] = sched_df[valid_off].apply(lambda x: x[x != ""].count(), axis=1) if valid_off else 0
        sched_df['Score'] = (sched_df['Off-Nights'] * 2) + (sched_df['Total'] - sched_df['Off-Nights'])
        
        sched_df = sched_df.sort_values(by=['Score', 'Total'], ascending=False)
        sched_df['Logo'] = sched_df.index.to_series().apply(get_team_logo)
        
        cols = ['Logo', 'Score', 'Total', 'Off-Nights'] + dates
        sched_df = sched_df[cols]

        def highlight_off(val): return 'background-color: #2e7b50; color: white' if val != "" else 'background-color: #262730; color: #555'
        def highlight_busy(val): return 'background-color: #8b6e28; color: white' if val != "" else 'background-color: #1e1e1e; color: #555'

        styler = sched_df.style
        if valid_off: styler = styler.map(highlight_off, subset=valid_off)
        busy = [d for d in dates if d not in valid_off]
        if busy: styler = styler.map(highlight_busy, subset=busy)
        styler = styler.background_gradient(cmap="Greens", subset=['Score'])
        
        st.dataframe(
            styler, height=800, width="stretch", # 🟢 Fixed Warning
            column_config={
                "Logo": st.column_config.ImageColumn("Team", width="small"),
                "Score": st.column_config.ProgressColumn("Stream Score", min_value=0, max_value=14, format="%d")
            }
        )
    else: st.warning("No schedule data.")

# =========================================
# TAB 3: WAR ROOM
# =========================================
with tab3:
    if not df.empty:
        c1, c2 = st.columns(2)
        with c1: p1 = st.selectbox("Player 1 (Give)", final['Player'].unique())
        with c2: p2 = st.selectbox("Player 2 (Receive)", final['Player'].unique(), index=1)

        p1_data = final[final['Player'] == p1].iloc[0]; p2_data = final[final['Player'] == p2].iloc[0]
        
        col_p1, col_vs, col_p2 = st.columns([2, 1, 2])
        with col_p1:
            st.markdown(f"<h3 style='text-align: center; color: #FF4B4B;'>{p1}</h3>", unsafe_allow_html=True)
            if p1_data['Headshot']: st.markdown(f"<div style='text-align: center;'><img src='{p1_data['Headshot']}' width='150' style='border-radius: 50%; border: 3px solid #FF4B4B;'></div>", unsafe_allow_html=True)
            st.metric("Total Value", f"{p1_data['Total Value']:.2f}")

        with col_vs:
            st.markdown("<h1 style='text-align: center; padding-top: 50px; font-size: 60px;'>VS</h1>", unsafe_allow_html=True)

        with col_p2:
            st.markdown(f"<h3 style='text-align: center; color: #00CC96;'>{p2}</h3>", unsafe_allow_html=True)
            if p2_data['Headshot']: st.markdown(f"<div style='text-align: center;'><img src='{p2_data['Headshot']}' width='150' style='border-radius: 50%; border: 3px solid #00CC96;'></div>", unsafe_allow_html=True)
            st.metric("Total Value", f"{p2_data['Total Value']:.2f}", delta=f"{(p2_data['Total Value'] - p1_data['Total Value']):.2f}")

        st.divider()

        # 🟢 FIX: Removed BarChartColumn here too, simplified.
        chart_cats = [c for c in cats if weights[c] > 0]
        if chart_cats:
            def get_vals(row, cats): return [row.get(f"{c}V", 0) for c in cats]
            vals1 = get_vals(p1_data, chart_cats); vals2 = get_vals(p2_data, chart_cats)
            
            fig = go.Figure()
            fig.add_trace(go.Scatterpolar(r=vals1 + [vals1[0]], theta=chart_cats + [chart_cats[0]], fill='toself', name=p1, line=dict(color='#FF4B4B')))
            fig.add_trace(go.Scatterpolar(r=vals2 + [vals2[0]], theta=chart_cats + [chart_cats[0]], fill='toself', name=p2, line=dict(color='#00CC96')))
            fig.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[-3, 3]), bgcolor='#0E1117'), 
                paper_bgcolor='#0E1117', font=dict(color='white'),
                height=500, margin=dict(t=20, b=20)
            )
            # 🟢 FIX: Replaced use_container_width with standard layout (plotly handles stretch by default)
            st.plotly_chart(fig) 

        analysis, verdict = generate_trade_analysis(p1, p1_data, p2, p2_data, cats, weights)
        st.markdown(f"""<div style="background-color: #1c1f26; padding: 20px; border-radius: 10px; border-left: 5px solid {'#00CC96' if 'ACCEPT' in verdict or 'WIN' in verdict else '#FF4B4B'};"><h2 style="margin:0;">VERDICT: {verdict}</h2></div>""", unsafe_allow_html=True)
        st.markdown(f"<br>{analysis}", unsafe_allow_html=True)

# =========================================
# TAB 4: GOALIES
# =========================================
with tab4:
    g_df = get_nhl_goalie_stats(season, stats_start_date)
    if not g_df.empty:
        r_g = calculate_z_scores(g_df, {'W': False, 'GAA': True, 'SV%': False, 'SHO': False})
        if 'Team' in r_g.columns: r_g['Logo'] = r_g['Team'].apply(get_team_logo)
        if 'playerId' in r_g.columns: r_g['Headshot'] = r_g.apply(get_headshot, axis=1)
            
        cols = ['Headshot', 'Logo', 'Player', 'Team', 'Value', 'GP', 'W', 'GAA', 'SV%', 'SHO']
        # 🟢 Apply heatmap to goalies too
        g_heatmap = ['Value', 'W', 'GAA', 'SV%', 'SHO']
        st.dataframe(
            r_g[cols].style.format("{:.2f}", subset=['Value', 'W']).background_gradient(cmap="RdYlGn", subset=g_heatmap),
            column_config={
                "Headshot": st.column_config.ImageColumn("Img", width="small"),
                "Logo": st.column_config.ImageColumn("Team", width="small"),
                "Value": st.column_config.ProgressColumn("Rank", min_value=-3, max_value=10, format="%.2f")
            },
            height=600, width="stretch", hide_index=True # 🟢 Fixed Warning
        )

# =========================================
# TAB 5: TRENDS
# =========================================
with tab5:
    if st.button("🚀 Run Trends"):
        with st.spinner("Crunching..."):
            df_s = get_nhl_skater_stats(season, None); df_r = get_nhl_skater_stats(season, str(date.today() - timedelta(days=30)))
            if not df_s.empty and not df_r.empty:
                for d in [df_s, df_r]:
                    for c in numeric_cols: 
                        if c in d.columns: d[c] = pd.to_numeric(d[c], errors='coerce').fillna(0).astype(int)
                
                df_s = df_s[df_s['Pos'].isin(selected_pos)]; df_r = df_r[df_r['Pos'].isin(selected_pos)]
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
                        hide_index=True, width="stretch" # 🟢 Fixed Warning
                    )
                with c2: 
                    st.subheader("❄️ Cooling Down")
                    st.dataframe(
                        trend.sort_values('Trend', ascending=True).head(20)[cols].style.format("{:.2f}", subset=['Trend', 'S_Val', 'R_Val']).background_gradient(cmap="Reds_r", subset=['Trend']),
                        column_config={"Logo": st.column_config.ImageColumn("Team", width="small"), "Headshot": st.column_config.ImageColumn("Img", width="small")},
                        hide_index=True, width="stretch" # 🟢 Fixed Warning
                    )

# =========================================
# TAB 6: WIRE HAWK
# =========================================
with tab6:
    from yahoo_bridge import fetch_yahoo_data # Import your new Supabase-powered bridge
    
    st.subheader("🦅 LIVE WIRE SYNC")
    col_sync, col_status = st.columns([1, 3])
    
    with col_sync:
        if st.button("🔄 Sync with Yahoo", use_container_width=True):
            with st.spinner("Connecting to Yahoo via Supabase..."):
                try:
                    fetch_yahoo_data()
                    st.success("Sync Complete!")
                    # Force a rerun to pick up the new csv data
                    st.rerun()
                except Exception as e:
                    st.error(f"Sync failed: {e}")
                    
    with col_status:
        st.caption("This pulls your current roster and the top 100 free agents directly from your Yahoo League using the credentials in your Supabase Auth Vault.")

    st.divider()

    # Original Upload Logic (Keep as a backup or for historical data)
    uploaded_file = st.file_uploader("📂 Or upload a manual yahoo_export.csv", type="csv")
    
    # Check if we have a fresh sync or an upload
    target_file = None
    if uploaded_file:
        target_file = uploaded_file
    else:
        try:
            # Check if the bridge just created a fresh local file
            target_file = "yahoo_export.csv"
        except:
            target_file = None

    if target_file and 'final' in locals() and not final.empty:
        try:
            y_data = pd.read_csv(target_file)
            # ... [Rest of your existing processing logic stays the same] ...
            final['match_key'] = final['Player'].str.lower().str.strip()
            y_data['match_key'] = y_data['name'].str.lower().str.strip()
            merged = pd.merge(y_data, final, left_on='match_key', right_on='match_key', how='inner')
            
            if 'Team' in merged.columns: merged['Logo'] = merged['Team'].apply(get_team_logo)
            if 'playerId' in merged.columns: merged['Headshot'] = merged.apply(get_headshot, axis=1)

            cols = ['Headshot', 'Logo', 'name', 'Team', 'Pos', 'Total Value'] + cats
            fa = merged[merged['Status'] == 'Free Agent'].sort_values('Total Value', ascending=False)
            ros = merged[merged['Status'] == 'Rostered'].sort_values('Total Value', ascending=False)
            
            wh_heatmap = ['Total Value'] + cats
            
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("💎 Free Agents")
                st.dataframe(
                    fa[cols].style.format("{:.2f}", subset=['Total Value']).background_gradient(cmap="RdYlGn", subset=wh_heatmap),
                    column_config={
                        "Logo": st.column_config.ImageColumn("Team", width="small"),
                        "Headshot": st.column_config.ImageColumn("Img", width="small"),
                        "Total Value": st.column_config.ProgressColumn("Val", min_value=-2, max_value=10, format="%.2f")
                    },
                    hide_index=True, width="stretch", height=600
                )
            with c2:
                st.subheader("📋 My Roster")
                st.dataframe(
                    ros[cols].style.format("{:.2f}", subset=['Total Value']).background_gradient(cmap="RdYlGn", subset=wh_heatmap),
                    column_config={
                        "Logo": st.column_config.ImageColumn("Team", width="small"),
                        "Headshot": st.column_config.ImageColumn("Img", width="small"),
                        "Total Value": st.column_config.ProgressColumn("Val", min_value=-2, max_value=10, format="%.2f")
                    },
                    hide_index=True, width="stretch", height=600
                )
        except Exception as e: 
            st.info("Waiting for Yahoo data... Click 'Sync with Yahoo' above to begin.")