import streamlit as st
import pandas as pd
from datetime import date, datetime
from data_fetcher import get_fantasy_weeks, get_nhl_schedule
from config import get_team_logo, get_headshot


def render(tab, final, cats, weights):
    with tab:
        st.subheader("🦅 THE WIRE HAWK")
        st.caption("Cross-references your synced league against the PuckNexus calculation engine.")

        if 'yahoo_data' not in st.session_state:
            st.info("Sync your Yahoo or ESPN league in the Control Center above.")
            return

        yahoo_df = st.session_state['yahoo_data']

        if final.empty:
            st.warning("No player data available.")
            return

        try:
            wire_df = final.copy()
            wire_df['match_key'] = wire_df['Player'].str.lower().str.strip()
            y_data = yahoo_df.copy()
            y_data['match_key'] = y_data['name'].str.lower().str.strip()

            cols_to_use = [c for c in wire_df.columns if c not in y_data.columns or c == 'match_key']
            merged = pd.merge(y_data, wire_df[cols_to_use], on='match_key', how='inner')
            merged = merged.drop_duplicates(subset=['match_key'])

            if 'Team' in merged.columns:   merged['Logo']     = merged['Team'].apply(get_team_logo)
            if 'playerId' in merged.columns: merged['Headshot'] = merged.apply(get_headshot, axis=1)

            fa  = merged[merged['Status'] == 'Free Agent'].sort_values('NexusScore', ascending=False)
            ros = merged[merged['Is_Mine'] == True].sort_values('NexusScore', ascending=False) \
                if 'Is_Mine' in merged.columns else \
                merged[merged['Status'] == 'Rostered'].sort_values('NexusScore', ascending=False)

            # Remaining schedule
            today_date = date.today()
            today_str  = str(today_date)
            weeks = get_fantasy_weeks()
            current_week = next((w for w in weeks if w['start'] <= today_date <= w['end']), weeks[0])
            end_str = str(current_week['end'])
            rem_sched = get_nhl_schedule(today_str)

            team_rem_games = {}
            team_rem_off   = {}
            if rem_sched:
                for d, games in rem_sched.items():
                    if today_str <= d <= end_str:
                        dt = datetime.strptime(d, "%Y-%m-%d")
                        is_off = dt.weekday() in [0, 2, 4, 6]
                        for team in games:
                            team_rem_games[team] = team_rem_games.get(team, 0) + 1
                            if is_off:
                                team_rem_off[team] = team_rem_off.get(team, 0) + 1

            fa['Rem G']     = fa['Team'].map(team_rem_games).fillna(0).astype(int)
            fa['Off-Nights'] = fa['Team'].map(team_rem_off).fillna(0).astype(int)

            # Advanced Scout
            active_cats = [c for c in cats if weights[c] > 0]
            if not ros.empty and not fa.empty and active_cats:
                team_analysis   = ros[[f"{c}V" for c in active_cats if f"{c}V" in ros.columns]].mean()
                if not team_analysis.empty:
                    weakest_cat_v = team_analysis.idxmin()
                    weakest_cat   = weakest_cat_v.replace('V', '')
                    playable_fa   = fa[fa['Rem G'] > 0]
                    if not playable_fa.empty and weakest_cat_v in playable_fa.columns:
                        best_fa = playable_fa.sort_values(by=[weakest_cat_v, 'Off-Nights'], ascending=[False, False]).iloc[0]
                        st.markdown(f"""
                            <div style="background-color:#1c1f26;padding:15px;border-radius:10px;border-left:5px solid #FF914D;margin-bottom:20px;">
                                <h3 style="margin:0;color:#FF914D;">🦅 ADVANCED SCOUT'S RECOMMENDATION</h3>
                                <p style="margin:10px 0 0 0;">Team Weakness: <b>{weakest_cat}</b> (Avg: {team_analysis[weakest_cat_v]:.2f}).<br>
                                Top FA Target: <b>{best_fa['name']}</b> ({best_fa[weakest_cat_v]:.2f} Category Score).<br>
                                <i style="color:#00CC96;">Schedule Edge: {best_fa['Rem G']} games remaining, <b>{best_fa['Off-Nights']} off-nights</b>.</i></p>
                            </div>
                        """, unsafe_allow_html=True)

            st.divider()
            heatmap_subset = ['NexusScore'] + cats

            st.subheader("📋 My Roster")
            ros_cols = [c for c in ['Headshot', 'Logo', 'name', 'Team', 'Pos', 'NexusScore'] + cats if c in ros.columns]
            st.dataframe(
                ros[ros_cols].style.format("{:.2f}", subset=['NexusScore'])
                .background_gradient(cmap="RdYlGn", subset=[c for c in heatmap_subset if c in ros_cols]),
                column_config={
                    "Logo":     st.column_config.ImageColumn("", width="small"),
                    "Headshot": st.column_config.ImageColumn("Pic", width="small"),
                    "name":     st.column_config.TextColumn("Player", width="medium"),
                    "Team":     st.column_config.TextColumn("Team", width="small"),
                    "NexusScore": st.column_config.NumberColumn("NexusScore", format="%.2f"),
                },
                hide_index=True, use_container_width=False
            )

            st.divider()
            st.subheader("💎 Free Agents")
            fa_cols = [c for c in ['Headshot', 'Logo', 'name', 'Team', 'Pos', 'Rem G', 'Off-Nights', 'NexusScore'] + cats if c in fa.columns]
            st.dataframe(
                fa[fa_cols].style.format("{:.2f}", subset=['NexusScore'])
                .background_gradient(cmap="RdYlGn", subset=[c for c in heatmap_subset if c in fa_cols]),
                column_config={
                    "Logo":     st.column_config.ImageColumn("", width="small"),
                    "Headshot": st.column_config.ImageColumn("Pic", width="small"),
                    "name":     st.column_config.TextColumn("Player", width="medium"),
                    "Team":     st.column_config.TextColumn("Team", width="small"),
                    "NexusScore": st.column_config.NumberColumn("NexusScore", format="%.2f"),
                },
                hide_index=True, use_container_width=False
            )

        except Exception as e:
            st.info(f"Sync your league to load data. ({e})")
