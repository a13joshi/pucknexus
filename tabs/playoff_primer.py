import streamlit as st
import pandas as pd
from datetime import datetime
from data_fetcher import get_nhl_schedule
from config import get_team_logo


def render(tab):
    with tab:
        st.header("🔮 PLAYOFF PRIMER: Championship Schedule Matrix")
        st.caption("Regular season wins get you to the dance, but playoff schedules win championships.")

        playoff_start = "2026-03-16"
        playoff_end   = "2026-04-05"
        st.markdown(f"**Targeting Playoff Window:** `{playoff_start}` to `{playoff_end}`")

        if st.button("🚀 Generate Playoff Matrix"):
            with st.spinner("Calculating the championship run..."):
                p_sched = get_nhl_schedule(playoff_start)

                if not p_sched:
                    st.warning("Could not load schedule data.")
                    return

                team_p_games = {}
                team_p_off   = {}

                for d, games in p_sched.items():
                    if playoff_start <= d <= playoff_end:
                        dt     = datetime.strptime(d, "%Y-%m-%d")
                        is_off = dt.weekday() in [0, 2, 4, 6]
                        for team in games:
                            team_p_games[team] = team_p_games.get(team, 0) + 1
                            if is_off:
                                team_p_off[team] = team_p_off.get(team, 0) + 1

                playoff_df = pd.DataFrame({
                    'Team':          list(team_p_games.keys()),
                    'Playoff Games': list(team_p_games.values()),
                    'Off-Nights':    [team_p_off.get(t, 0) for t in team_p_games],
                })
                playoff_df['Championship Score'] = (
                    playoff_df['Off-Nights'] * 2 +
                    (playoff_df['Playoff Games'] - playoff_df['Off-Nights'])
                )
                playoff_df = playoff_df.sort_values(
                    by=['Championship Score', 'Playoff Games'], ascending=[False, False]
                )
                playoff_df['Logo'] = playoff_df['Team'].apply(get_team_logo)

                col_ranks, col_advice = st.columns([2, 1])
                with col_ranks:
                    st.subheader("📊 Playoff Schedule Strength")
                    st.dataframe(
                        playoff_df[['Logo', 'Team', 'Championship Score', 'Playoff Games', 'Off-Nights']]
                        .style.background_gradient(cmap="Purples", subset=['Championship Score', 'Off-Nights']),
                        column_config={
                            "Logo": st.column_config.ImageColumn("Team", width="small"),
                            "Championship Score": st.column_config.ProgressColumn("Edge", min_value=0, max_value=20, format="%d"),
                        },
                        hide_index=True, use_container_width=True, height=600
                    )
                with col_advice:
                    st.subheader("💡 Trade Deadline Advice")
                    top_teams    = playoff_df.head(3)['Team'].tolist()
                    bottom_teams = playoff_df.tail(3)['Team'].tolist()
                    st.success(f"**BUY TARGETS:** Players from **{', '.join(top_teams)}**. Best playoff volume + off-nights.")
                    st.error(f"**SELL CANDIDATES:** Players from **{', '.join(bottom_teams)}**. Light playoff schedule.")
