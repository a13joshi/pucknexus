import streamlit as st
import pandas as pd
from data_fetcher import get_multi_week_schedule


def render(tab):
    with tab:
        st.header("📅 Multi-Week Schedule Grid")
        st.caption("Game counts and off-nights per team for upcoming fantasy weeks. Green = 4+ games, Yellow = 3 games, Red = 2 or fewer.")

        try:
            col_left, col_right = st.columns([3, 1])
            with col_left:
                lookahead = st.slider("Weeks to display", min_value=1, max_value=8, value=4)
            with col_right:
                show_offnights = st.checkbox("Show off-nights", value=True)

            with st.spinner("Loading schedule data..."):
                week_data, future_weeks = get_multi_week_schedule(lookahead)

            if week_data:
                all_teams = set()
                for w in future_weeks[:lookahead]:
                    all_teams.update(week_data.get(w['label'], {}).keys())

                rows = []
                for team in sorted(all_teams):
                    row = {'Team': team}
                    total_gp = 0
                    total_off = 0
                    for w in future_weeks[:lookahead]:
                        td = week_data.get(w['label'], {}).get(team, {})
                        gp  = td.get('GP', 0)
                        off = td.get('OFF', 0)
                        total_gp  += gp
                        total_off += off
                        row[w['label']] = f"{gp}G / {off}off" if show_offnights else f"{gp}G"
                    row['Total GP']   = total_gp
                    row['Off-Nights'] = total_off
                    rows.append(row)

                grid_df  = pd.DataFrame(rows).sort_values('Total GP', ascending=False)
                week_cols = [w['label'] for w in future_weeks[:lookahead]]

                def color_cell(val):
                    try:
                        gp = int(str(val).split('G')[0])
                        if gp >= 4: return 'background-color:#1a4a2e; color:white'
                        elif gp == 3: return 'background-color:#4a3a00; color:white'
                        else: return 'background-color:#4a1a1a; color:white'
                    except Exception:
                        return ''

                styled = (
                    grid_df.style
                    .applymap(color_cell, subset=week_cols)
                    .background_gradient(cmap='Greens', subset=['Total GP'])
                )
                st.dataframe(styled, hide_index=True, use_container_width=True,
                             height=min(60 + len(grid_df) * 35, 800))
                st.caption("🟢 4+ games &nbsp;&nbsp; 🟡 3 games &nbsp;&nbsp; 🔴 ≤2 games &nbsp;&nbsp; Off-nights = Mon/Wed/Fri/Sun")
            else:
                st.warning("Could not load schedule data.")

        except Exception as e:
            st.warning(f"Could not load schedule: {e}")
