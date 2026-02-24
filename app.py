import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
from data_fetcher import get_nhl_skater_stats, get_nhl_goalie_stats, get_nhl_schedule, get_fantasy_weeks
from monster_math import calculate_z_scores

# --- GLOBAL CONFIG ---
st.set_page_config(page_title="PuckNexus 4.0", layout="wide")
st.title("🏒 PuckNexus 4.0")
st.markdown("The **Unofficial** Fantasy Hockey Expansion")

# --- GLOBAL SIDEBAR ---
st.sidebar.header("⚙️ Global Settings")
season = st.sidebar.selectbox("Season", ["20252026", "20242025"])

# Timeframe Logic
timeframe = st.sidebar.selectbox("📅 Timeframe", ["Full Season", "Last 14 Days", "Last 30 Days"])
stats_start_date = None
if timeframe == "Last 14 Days":
    stats_start_date = str(date.today() - timedelta(days=14))
elif timeframe == "Last 30 Days":
    stats_start_date = str(date.today() - timedelta(days=30))

st.sidebar.caption(f"Analyzing: **{timeframe}**")

# Punts
st.sidebar.subheader("Punt Strategy (Skaters)")
cats = ['G', 'A', '+/-', 'PIM', 'PPP', 'SOG', 'HIT', 'BLK']
weights = {cat: 1.0 if st.sidebar.checkbox(f"Count {cat}", value=True) else 0.0 for cat in cats}

# --- HELPER: AI GM LOGIC ---
def generate_trade_analysis(p1_name, p1_data, p2_name, p2_data, cats, weights):
    """
    Generates a text-based analysis of the trade.
    """
    gains = []
    losses = []
    push = []

    for c in cats:
        if weights[c] == 0: continue # Skip punted cats
        
        diff = p2_data[f"{c}V"] - p1_data[f"{c}V"]
        
        # Thresholds for "Significant" change
        if diff > 0.5:
            gains.append(c)
        elif diff < -0.5:
            losses.append(c)
        else:
            push.append(c)
            
    # Construct Narrative
    summary = f"**Trade Analysis:** Sending **{p1_name}** for **{p2_name}**.\n\n"
    
    if not gains and not losses:
        summary += "😐 **Lateral Move:** This trade is statistically very similar. It may come down to personal preference or schedule."
    else:
        if gains:
            summary += f"✅ **You Gain:** Significant boost in **{', '.join(gains)}**.\n"
        if losses:
            summary += f"⚠️ **You Lose:** Expect a drop in **{', '.join(losses)}**.\n"
            
    # Verdict
    val_diff = p2_data['Total Value'] - p1_data['Total Value']
    if val_diff > 1.0:
        summary += "\n🔥 **Verdict: SMASH ACCEPT.** The math overwhelmingly favors the player you are receiving."
    elif val_diff > 0:
        summary += "\n👍 **Verdict: Slight Win.** You come out ahead mathematically, but check if the category losses hurt your team build."
    elif val_diff > -1.0:
        summary += "\n🤔 **Verdict: Slight Loss.** You are losing value, but it might be worth it if you specifically need the categories you are gaining."
    else:
        summary += "\n🛑 **Verdict: REJECT.** You are losing significant value across the board."
        
    return summary

# --- TABS ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 Skaters", "📅 Schedule", "⚖️ War Room", "🥅 Goalies", "📈 Trends", "🦅 Wire Hawk"])

# Shared Data Cache
@st.cache_data
def load_skaters(s, start_d): return get_nhl_skater_stats(s, start_d)

# =========================================
# TAB 1: SKATERS
# =========================================
with tab1:
    st.header("🏆 Skater Rankings")
    
    col1, col2 = st.columns(2)
    with col1: selected_pos = st.multiselect("Filter Position", ['C', 'L', 'R', 'D'], default=['C', 'L', 'R', 'D'])
    with col2: view_mode = st.radio("View Mode:", ["Per Game Value", "Total Value"], horizontal=True)

    with st.spinner('Scouting skaters...'):
        df = load_skaters(season, stats_start_date)
        if df is not None: df = df.copy()

    if not df.empty:
        df.columns = df.columns.str.strip()
        numeric_cols = ['GP', 'G', 'A', 'PTS', '+/-', 'PIM', 'PPP', 'SOG', 'HIT', 'BLK']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

        df = df[df['Pos'].isin(selected_pos)] if 'Pos' in df.columns else df
        ranked = calculate_z_scores(df, cats)
        
        ranked['Total Value'] = sum(ranked.get(f"{c}V", 0) * weights[c] for c in cats)
        final = ranked.sort_values(by="Total Value", ascending=False)
        
        display_cols = ['Player', 'Team', 'Pos', 'GP', 'G', 'A', 'PTS', '+/-', 'PIM', 'PPP', 'SOG', 'HIT', 'BLK', 'Total Value']
        actual_cols = [c for c in display_cols if c in final.columns]
        
        st.dataframe(
            final[actual_cols].style.format("{:.2f}", subset=['Total Value'])
                 .background_gradient(cmap="RdYlGn", subset=['Total Value']),
            height=700, width='stretch'
        )
    else: st.error("No skater data found.")

# =========================================
# TAB 2: SCHEDULE OPTIMIZER
# =========================================
with tab2:
    st.header("📅 Schedule Optimizer")
    sched_data = get_nhl_schedule(str(date.today()))
    
    if sched_data:
        all_teams = set()
        dates = sorted(sched_data.keys())
        matrix = {} 
        
        for d in dates:
            games = sched_data[d]
            for team, opp in games.items():
                all_teams.add(team)
                if team not in matrix: matrix[team] = {}
                matrix[team][d] = opp

        if not all_teams:
            st.warning("No games found for the upcoming week.")
        else:
            sched_df = pd.DataFrame.from_dict(matrix, orient='index')
            sched_df = sched_df.reindex(index=list(all_teams), columns=dates).fillna("")
            sched_df['Games'] = sched_df.apply(lambda x: x[x != ""].count(), axis=1)
            sched_df = sched_df.sort_values(by='Games', ascending=False)

            st.caption("Maximize your roster starts! Darker rows = More games this week.")
            def highlight_games(val):
                return 'background-color: #2e7b50; color: white' if val != "" else 'background-color: #1e1e1e; color: #555'

            st.dataframe(
                sched_df.style.map(highlight_games, subset=dates)
                        .background_gradient(cmap="Greens", subset=['Games']),
                width='stretch', height=800
            )
    else:
        st.warning("No schedule data found.")

# =========================================
# TAB 3: WAR ROOM (AI GM)
# =========================================
with tab3:
    st.header("⚖️ The War Room")
    
    if not df.empty:
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            p1 = st.selectbox("Player 1 (Give)", final['Player'].unique())
        with col_t2:
            p2 = st.selectbox("Player 2 (Receive)", final['Player'].unique(), index=1 if len(final) > 1 else 0)

        p1_data = final[final['Player'] == p1].iloc[0]
        p2_data = final[final['Player'] == p2].iloc[0]

        # --- RADAR CHART ---
        chart_cats = [c for c in cats if weights[c] > 0]
        
        def get_chart_values(player_row, categories):
            vals = []
            for c in categories:
                z = player_row.get(f"{c}V", 0)
                vals.append(z)
            return vals

        p1_vals = get_chart_values(p1_data, chart_cats)
        p2_vals = get_chart_values(p2_data, chart_cats)
        
        chart_cats_closed = chart_cats + [chart_cats[0]]
        p1_vals_closed = p1_vals + [p1_vals[0]]
        p2_vals_closed = p2_vals + [p2_vals[0]]

        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(
            r=p1_vals_closed, theta=chart_cats_closed, fill='toself', name=p1,
            line=dict(color='salmon')
        ))
        fig.add_trace(go.Scatterpolar(
            r=p2_vals_closed, theta=chart_cats_closed, fill='toself', name=p2,
            line=dict(color='cyan')
        ))

        fig.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[-3, 3])),
            showlegend=True,
            title="Relative Value (Z-Scores)",
            height=500
        )
        
        st.plotly_chart(fig, width="stretch")

        # --- AI GM ANALYSIS ---
        st.divider()
        st.subheader("🤖 AI Scouting Report")
        ai_report = generate_trade_analysis(p1, p1_data, p2, p2_data, cats, weights)
        st.info(ai_report)
        
    else:
        st.info("Load skater data in Tab 1 to enable trade analysis.")

# =========================================
# TAB 4: GOALIES
# =========================================
with tab4:
    st.header("🥅 Goalie Rankings")
    
    with st.spinner('Fetching netminder stats...'):
        goalie_df = get_nhl_goalie_stats(season, stats_start_date)
    
    if goalie_df is not None and not goalie_df.empty:
        goalie_cats = {'W': False, 'GAA': True, 'SV%': False, 'SHO': False}
        ranked_goalies = calculate_z_scores(goalie_df, goalie_cats)
        
        st.dataframe(
            ranked_goalies.style.format({
                'Value': "{:.2f}", 
                'GAA': "{:.3f}", 
                'SV%': "{:.3f}",
                'WV': "{:.2f}", 'GAAV': "{:.2f}", 'SV%V': "{:.2f}", 'SHOV': "{:.2f}"
            }).background_gradient(cmap="RdYlGn", subset=['Value']),
            height=600, width='stretch'
        )
    else:
        st.error("No goalie data found.")

# =========================================
# TAB 5: TRENDS
# =========================================
with tab5:
    st.header("📈 Hot & Cold Trends")
    st.caption("Comparing **Season Average** vs **Last 30 Days**.")
    
    if st.button("🚀 Run Trend Analysis"):
        with st.spinner("Crunching numbers..."):
            df_season = get_nhl_skater_stats(season, None)
            l30_date = str(date.today() - timedelta(days=30))
            df_recent = get_nhl_skater_stats(season, l30_date)
            
            if not df_season.empty and not df_recent.empty:
                for d in [df_season, df_recent]:
                    for c in numeric_cols:
                        if c in d.columns: d[c] = pd.to_numeric(d[c], errors='coerce').fillna(0).astype(int)
                
                df_season = df_season[df_season['Pos'].isin(selected_pos)]
                df_recent = df_recent[df_recent['Pos'].isin(selected_pos)]

                z_season = calculate_z_scores(df_season, cats)
                z_recent = calculate_z_scores(df_recent, cats)
                
                z_season['Season_Val'] = sum(z_season.get(f"{c}V", 0) * weights[c] for c in cats)
                z_recent['Recent_Val'] = sum(z_recent.get(f"{c}V", 0) * weights[c] for c in cats)
                
                # Merge on playerId, keeping names
                trend_df = pd.merge(
                    z_season[['playerId', 'Player', 'Team', 'Season_Val']], 
                    z_recent[['playerId', 'Recent_Val']], 
                    on='playerId', how='inner'
                )
                
                trend_df['Trend'] = trend_df['Recent_Val'] - trend_df['Season_Val']
                
                col_hot, col_cold = st.columns(2)
                with col_hot:
                    st.subheader("🔥 Heating Up")
                    risers = trend_df.sort_values(by="Trend", ascending=False).head(20)
                    st.dataframe(risers.style.format("{:.2f}", subset=['Season_Val', 'Recent_Val', 'Trend']).background_gradient(cmap="Greens", subset=['Trend']), width='stretch')
                    
                with col_cold:
                    st.subheader("❄️ Cooling Down")
                    fallers = trend_df.sort_values(by="Trend", ascending=True).head(20)
                    st.dataframe(fallers.style.format("{:.2f}", subset=['Season_Val', 'Recent_Val', 'Trend']).background_gradient(cmap="Reds_r", subset=['Trend']), width='stretch')
            else:
                st.error("Could not fetch data for trend analysis.")

# =========================================
# TAB 6: WIRE HAWK (YAHOO INTEGRATED)
# =========================================
with tab6:
    st.header("🦅 Wire Hawk (Yahoo Integrated)")
    st.markdown("Upload the **`yahoo_export.csv`** generated by your `yahoo_bridge.py` script to instantly rank your actual free agents.")
    
    uploaded_file = st.file_uploader("📂 Drag & Drop yahoo_export.csv here", type="csv")
    
    # We check if 'final' exists in the local scope (it should if Tab 1 ran successfully)
    if uploaded_file is not None and 'final' in locals() and not final.empty:
        # 1. Load Yahoo Data
        try:
            yahoo_data = pd.read_csv(uploaded_file)
            
            # 2. Match with NHL Stats
            # 🟢 FIX: Add 'match_key' to 'final' (the dataframe we actually merge with), not 'df'
            final['match_key'] = final['Player'].str.lower().str.strip()
            yahoo_data['match_key'] = yahoo_data['name'].str.lower().str.strip()
            
            merged = pd.merge(yahoo_data, final, left_on='match_key', right_on='match_key', how='inner')
            
            # 3. Filter for Free Agents Only
            free_agents = merged[merged['Status'] == 'Free Agent'].sort_values(by='Total Value', ascending=False)
            my_roster = merged[merged['Status'] == 'Rostered'].sort_values(by='Total Value', ascending=False)
            
            col_fa, col_roster = st.columns(2)
            
            with col_fa:
                st.subheader("💎 Top Available Free Agents")
                st.dataframe(
                    free_agents[['name', 'Team', 'Pos', 'Total Value'] + cats]
                    .style.format("{:.2f}", subset=['Total Value'])
                    .background_gradient(cmap="Greens", subset=['Total Value']), 
                    height=600
                )
                
            with col_roster:
                st.subheader("📋 Your Current Roster")
                st.dataframe(
                    my_roster[['name', 'Team', 'Pos', 'Total Value'] + cats]
                    .style.format("{:.2f}", subset=['Total Value'])
                    .background_gradient(cmap="Blues", subset=['Total Value']), 
                    height=600
                )
        except Exception as e:
            st.error(f"Error reading file: {e}")
            
    elif uploaded_file is None:
        st.info("Waiting for file upload...")
    else:
        st.error("Please load skater data in Tab 1 first.")