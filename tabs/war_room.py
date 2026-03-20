import streamlit as st
import pandas as pd
from datetime import date
from data_fetcher import get_fantasy_weeks, get_nhl_schedule
from config import get_team_logo, get_headshot


def render(tab, final, cats, weights):
    with tab:
        st.header("⚖️ WAR ROOM: Blockbuster Trade Machine")

        if final.empty:
            st.warning("No data available for player comparison.")
            return

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
                st.markdown("<h3 style='text-align:center;color:#FF4B4B;'>Team A Package</h3>", unsafe_allow_html=True)
                for _, row in p1_data.iterrows():
                    st.markdown(f"**{row['Player']}** ({row['Pos']}): {row['NexusScore']:.2f} Nexus")
                st.metric("Total Package Value", f"{p1_total:.2f}")
            with col_vs:
                st.markdown("<h1 style='text-align:center;padding-top:50px;font-size:60px;'>VS</h1>", unsafe_allow_html=True)
            with col_p2:
                st.markdown("<h3 style='text-align:center;color:#00CC96;'>Team B Package</h3>", unsafe_allow_html=True)
                for _, row in p2_data.iterrows():
                    st.markdown(f"**{row['Player']}** ({row['Pos']}): {row['NexusScore']:.2f} Nexus")
                st.metric("Total Package Value", f"{p2_total:.2f}", delta=f"{(p2_total - p1_total):.2f}")

            st.divider()

            if len(p1_list) != len(p2_list):
                st.warning(f"⚠️ **Uneven Trade Detected:** {len(p1_list)}-for-{len(p2_list)} swap.")

            diff = p2_total - p1_total
            if diff > 1.0:   verdict, v_color = "🔥 ACCEPT: Clear Upgrade", "#00CC96"
            elif diff < -1.0: verdict, v_color = "❌ DECLINE: Massive Value Loss", "#FF4B4B"
            else:             verdict, v_color = "⚖️ NEUTRAL: Fair Swap or Needs Context", "#FF914D"

            st.markdown(f"""
                <div style="background-color:#1c1f26;padding:20px;border-radius:10px;border-left:5px solid {v_color};">
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
            end_str   = str(current_week['end'])
            week_sched = get_nhl_schedule(start_str)

            def count_games(team_abbr, schedule_dict):
                if not schedule_dict: return 0
                return sum(1 for day, games in schedule_dict.items() if start_str <= day <= end_str and team_abbr in games)

            p1_games = sum(count_games(row['Team'], week_sched) for _, row in p1_data.iterrows())
            p2_games = sum(count_games(row['Team'], week_sched) for _, row in p2_data.iterrows())
            p1_proj  = sum(row['NexusScore'] * count_games(row['Team'], week_sched) for _, row in p1_data.iterrows())
            p2_proj  = sum(row['NexusScore'] * count_games(row['Team'], week_sched) for _, row in p2_data.iterrows())

            col_m1, col_m2 = st.columns(2)
            with col_m1: st.metric(f"Team A ({p1_games} games)", f"{p1_proj:.2f} Nexus")
            with col_m2: st.metric(f"Team B ({p2_games} games)", f"{p2_proj:.2f} Nexus", delta=f"{(p2_proj - p1_proj):.2f}")
            st.caption(f"Projected for Fantasy Week: {start_str} to {end_str}")

        else:
            st.info("Select at least one player for both teams to analyze the trade.")

        st.divider()
        st.header("🚦 DAILY START / SIT OPTIMIZER")
        st.caption("Select players competing for your active roster spots tonight.")

        bench_mob = st.multiselect("Select Players to Compare", final['Player'].unique(), key="bench_select")

        if bench_mob:
            today_str  = str(date.today())
            daily_sched = get_nhl_schedule(today_str)
            todays_games = daily_sched.get(today_str, {}) if daily_sched else {}

            bench_data = final[final['Player'].isin(bench_mob)].copy()
            bench_data['Plays Tonight'] = bench_data['Team'].apply(lambda t: "Yes" if t in todays_games else "No")
            bench_data['Opponent']      = bench_data['Team'].apply(lambda t: todays_games.get(t, "N/A"))

            sort_col   = 'VORP' if 'VORP' in bench_data.columns else 'NexusScore'
            bench_data = bench_data.sort_values(by=['Plays Tonight', sort_col], ascending=[False, False])

            active_players = bench_data[bench_data['Plays Tonight'] == 'Yes']
            if not active_players.empty:
                top = active_players.iloc[0]
                st.success(f"**START:** {top['Player']} vs {top['Opponent']} (Value: {top[sort_col]:.2f})")
                st.dataframe(
                    bench_data[['Headshot', 'Player', 'Team', 'Plays Tonight', 'Opponent', sort_col]],
                    column_config={"Headshot": st.column_config.ImageColumn("Img", width="small")},
                    hide_index=True, use_container_width=True
                )
            else:
                st.warning("None of the selected players have a game tonight.")
