import streamlit as st
import pandas as pd
from datetime import date, timedelta
from data_fetcher import get_nhl_skater_stats
from monster_math import calculate_z_scores
from config import get_team_logo, get_headshot


def render(tab, calc_season, cats, weights, selected_pos):
    with tab:
        if st.button("🚀 Run Trends"):
            with st.spinner("Crunching..."):
                df_s = get_nhl_skater_stats(calc_season, None)
                df_r = get_nhl_skater_stats(calc_season, str(date.today() - timedelta(days=30)))

                if not df_s.empty and not df_r.empty:
                    numeric_cols = ['G', 'A', 'SOG', 'HIT', 'BLK', 'PIM', 'PPP', '+/-']
                    for d in [df_s, df_r]:
                        for c in numeric_cols:
                            if c in d.columns:
                                d[c] = pd.to_numeric(d[c], errors='coerce').fillna(0)

                    df_s = df_s[df_s['Pos'].isin(selected_pos)]
                    df_r = df_r[df_r['Pos'].isin(selected_pos)]

                    z_s = calculate_z_scores(df_s, cats)
                    z_r = calculate_z_scores(df_r, cats)
                    z_s['S_Val'] = sum(z_s.get(f"{c}V", 0) * weights[c] for c in cats)
                    z_r['R_Val'] = sum(z_r.get(f"{c}V", 0) * weights[c] for c in cats)

                    trend = pd.merge(
                        z_s[['playerId', 'Player', 'Team', 'S_Val']],
                        z_r[['playerId', 'R_Val']], on='playerId'
                    )
                    trend['Trend']   = trend['R_Val'] - trend['S_Val']
                    trend['Logo']    = trend['Team'].apply(get_team_logo)
                    trend['Headshot'] = trend.apply(get_headshot, axis=1)

                    cols = ['Headshot', 'Logo', 'Player', 'Trend', 'S_Val', 'R_Val']
                    img_cfg = {
                        "Logo":     st.column_config.ImageColumn("Team", width="small"),
                        "Headshot": st.column_config.ImageColumn("Img",  width="small"),
                    }

                    c1, c2 = st.columns(2)
                    with c1:
                        st.subheader("🔥 Heating Up")
                        st.dataframe(
                            trend.sort_values('Trend', ascending=False).head(20)[cols]
                            .style.format("{:.2f}", subset=['Trend', 'S_Val', 'R_Val'])
                            .background_gradient(cmap="Greens", subset=['Trend']),
                            column_config=img_cfg, hide_index=True, use_container_width=True
                        )
                    with c2:
                        st.subheader("❄️ Cooling Down")
                        st.dataframe(
                            trend.sort_values('Trend', ascending=True).head(20)[cols]
                            .style.format("{:.2f}", subset=['Trend', 'S_Val', 'R_Val'])
                            .background_gradient(cmap="Reds_r", subset=['Trend']),
                            column_config=img_cfg, hide_index=True, use_container_width=True
                        )
