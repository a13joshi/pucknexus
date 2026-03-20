import streamlit as st
import pandas as pd
from datetime import date, timedelta
from data_fetcher import get_nhl_skater_stats, get_nhl_goalie_stats, get_nhl_schedule, get_fantasy_weeks
from config import DEFAULT_G_CATS


def render(tab, s_df_global, g_df_global, cats, g_cats, weights, calc_season, timeframe, projection_mode="Season Stats"):
    with tab:
        st.header("⚔️ H2H Matchup Simulator")
        try:
            if 'yahoo_data' not in st.session_state:
                st.info("Sync your Yahoo or ESPN league in the Control Center above.")
                return

            yahoo_df = st.session_state['yahoo_data']
            yahoo_df['match_key'] = yahoo_df['name'].str.lower().str.strip()

            my_team_name = (
                yahoo_df[yahoo_df['Is_Mine'] == True]['Fantasy_Team'].iloc[0]
                if 'Is_Mine' in yahoo_df.columns and not yahoo_df[yahoo_df['Is_Mine'] == True].empty
                else None
            )

            teams = sorted(yahoo_df['Fantasy_Team'].dropna().unique())

            if len(teams) < 2:
                st.info("Not enough teams found. Ensure you have run the sync.")
                return

            col1, col2 = st.columns(2)
            default_idx_a = teams.index(my_team_name) if my_team_name and my_team_name in teams else 0
            default_idx_b = 1 if default_idx_a == 0 else 0

            with col1: team_a = st.selectbox("Team A", teams, index=default_idx_a)
            with col2: team_b = st.selectbox("Team B", teams, index=default_idx_b)

            if st.button("🔮 Run Live Matchup Engine", use_container_width=True):
                with st.spinner(f"Crunching live weekly stats based on {timeframe} trends..."):

                    # 1. DATE LOGIC
                    today_date   = date.today()
                    yesterday_str = str(today_date - timedelta(days=1))
                    today_str    = str(today_date)
                    weeks        = get_fantasy_weeks()
                    current_week = next((w for w in weeks if w['start'] <= today_date <= w['end']), weeks[0])
                    start_str    = str(current_week['start'])
                    end_str      = str(current_week['end'])
                    cw_end_str   = today_str if yesterday_str < start_str else yesterday_str

                    active_cats   = [c for c in cats if weights[c] > 0]
                    available_g   = [c for c in ['W', 'GAA', 'SV%', 'SHO'] if c in g_df_global.columns]
                    active_g_cats = [c for c in available_g if weights.get(c, 1.0) > 0] or available_g

                    # 2. CURRENT WEEK STATS
                    cw_df = get_nhl_skater_stats(calc_season, start_date=start_str, end_date=cw_end_str)
                    if not cw_df.empty:
                        cw_df['match_key'] = cw_df['Player'].str.lower().str.strip()
                    else:
                        cw_df = pd.DataFrame(columns=['match_key'] + active_cats)

                    g_cw_df = get_nhl_goalie_stats(calc_season, start_date=start_str, end_date=cw_end_str)
                    if not g_cw_df.empty:
                        g_cw_df['match_key'] = g_cw_df['Player'].str.lower().str.strip()

                    # 3. PROJECTIONS
                    proj_df = s_df_global.copy()
                    proj_df['match_key'] = proj_df['Player'].str.lower().str.strip()
                    for c in active_cats:
                        if c in proj_df.columns:
                            proj_df[c] = pd.to_numeric(proj_df[c], errors='coerce').fillna(0)
                            proj_df[f"{c}_pg"] = proj_df[c] / proj_df['GP'].clip(lower=1)
                        else:
                            proj_df[f"{c}_pg"] = 0.0

                    g_proj_df = g_df_global.copy()
                    g_proj_df['match_key'] = g_proj_df['Player'].str.lower().str.strip()
                    for c in active_g_cats:
                        if c in g_proj_df.columns:
                            g_proj_df[c] = pd.to_numeric(g_proj_df[c], errors='coerce').fillna(0)
                            g_proj_df[f"{c}_pg"] = g_proj_df[c] / g_proj_df['GP'].clip(lower=1)
                        else:
                            g_proj_df[f"{c}_pg"] = 0.0

                    # 4. REMAINING SCHEDULE
                    rem_sched = get_nhl_schedule(today_str)
                    def get_rem_games(nhl_team):
                        if not rem_sched: return 0
                        return sum(1 for day, games in rem_sched.items() if today_str <= day <= end_str and nhl_team in games)

                    proj_df['Rem_G']   = proj_df['Team'].apply(get_rem_games)
                    g_proj_df['Rem_G'] = g_proj_df['Team'].apply(get_rem_games)

                    # 5. ROSTER SPLITS
                    roster_a = yahoo_df[(yahoo_df['Fantasy_Team'] == team_a) & (yahoo_df['Status'] == 'Rostered')]
                    roster_b = yahoo_df[(yahoo_df['Fantasy_Team'] == team_b) & (yahoo_df['Status'] == 'Rostered')]

                    # 6. SKATER TOTALS
                    def merge_cw(roster, cw):
                        return pd.merge(roster, cw, on='match_key', how='inner') if not cw.empty else pd.DataFrame()

                    a_cw = merge_cw(roster_a, cw_df)
                    b_cw = merge_cw(roster_b, cw_df)
                    a_proj = pd.merge(roster_a, proj_df, on='match_key', how='inner')
                    b_proj = pd.merge(roster_b, proj_df, on='match_key', how='inner')

                    a_cur = {c: a_cw[c].sum() if c in a_cw.columns else 0 for c in active_cats}
                    b_cur = {c: b_cw[c].sum() if c in b_cw.columns else 0 for c in active_cats}
                    a_rem = {c: sum(r[f"{c}_pg"] * r['Rem_G'] for _, r in a_proj.iterrows()) for c in active_cats}
                    b_rem = {c: sum(r[f"{c}_pg"] * r['Rem_G'] for _, r in b_proj.iterrows()) for c in active_cats}

                    # 7. GOALIE TOTALS
                    a_gcw  = merge_cw(roster_a, g_cw_df)
                    b_gcw  = merge_cw(roster_b, g_cw_df)
                    a_gproj = pd.merge(roster_a, g_proj_df, on='match_key', how='inner')
                    b_gproj = pd.merge(roster_b, g_proj_df, on='match_key', how='inner')

                    a_cur_g = {c: a_gcw[c].sum() if c in a_gcw.columns else 0 for c in active_g_cats}
                    b_cur_g = {c: b_gcw[c].sum() if c in b_gcw.columns else 0 for c in active_g_cats}
                    a_rem_g = {c: sum(r[f"{c}_pg"] * r['Rem_G'] for _, r in a_gproj.iterrows()) for c in active_g_cats}
                    b_rem_g = {c: sum(r[f"{c}_pg"] * r['Rem_G'] for _, r in b_gproj.iterrows()) for c in active_g_cats}

                    # 8. COMPILE
                    current_data, rem_data, final_data = [], [], []
                    a_wins, b_wins, ties = 0, 0, 0

                    for c in active_cats:
                        a_tot = a_cur[c] + a_rem[c]
                        b_tot = b_cur[c] + b_rem[c]
                        current_data.append({'Category': c, team_a: a_cur[c], team_b: b_cur[c]})
                        rem_data.append({'Category': c, team_a: a_rem[c], team_b: b_rem[c]})
                        if a_tot > b_tot:   winner, a_wins = team_a, a_wins + 1
                        elif b_tot > a_tot: winner, b_wins = team_b, b_wins + 1
                        else:               winner, ties   = "Tie", ties + 1
                        final_data.append({'Category': c, team_a: a_tot, team_b: b_tot, 'Winner': winner})

                    for c in active_g_cats:
                        a_tot = a_cur_g.get(c, 0) + a_rem_g.get(c, 0)
                        b_tot = b_cur_g.get(c, 0) + b_rem_g.get(c, 0)
                        current_data.append({'Category': c, team_a: a_cur_g.get(c, 0), team_b: b_cur_g.get(c, 0)})
                        rem_data.append({'Category': c, team_a: a_rem_g.get(c, 0), team_b: b_rem_g.get(c, 0)})
                        if c == 'GAA':
                            if a_tot < b_tot:   winner, a_wins = team_a, a_wins + 1
                            elif b_tot < a_tot: winner, b_wins = team_b, b_wins + 1
                            else:               winner, ties   = "Tie", ties + 1
                        else:
                            if a_tot > b_tot:   winner, a_wins = team_a, a_wins + 1
                            elif b_tot > a_tot: winner, b_wins = team_b, b_wins + 1
                            else:               winner, ties   = "Tie", ties + 1
                        final_data.append({'Category': c, team_a: a_tot, team_b: b_tot, 'Winner': winner})

                    # 9. UI
                    color = '#00CC96' if a_wins > b_wins else ('#FF914D' if a_wins == b_wins else '#FF4B4B')
                    st.markdown(f"""
                        <div style="background-color:#1c1f26;padding:20px;border-radius:10px;border-left:5px solid {color};text-align:center;margin-bottom:20px;">
                            <h3 style="margin:0;color:#888;">Projected Final: {team_a} vs {team_b}</h3>
                            <h1 style="margin:0;font-size:50px;">{a_wins} - {b_wins} - {ties}</h1>
                        </div>
                    """, unsafe_allow_html=True)

                    col_cur, col_rem = st.columns(2)
                    with col_cur:
                        st.subheader("🏒 Current Weekly Score")
                        st.caption(f"Stats from {start_str} to {cw_end_str}.")
                        df_cur = pd.DataFrame(current_data)
                        cur_total = df_cur[[team_a, team_b]].sum().sum()
                        if cur_total == 0:
                            st.info("⏳ Week just started — no stats yet. Check back after tonight's games.")
                        else:
                            st.dataframe(
                                df_cur.style.highlight_max(subset=[team_a, team_b], color='#2e7b50', axis=1)
                                .format({team_a: "{:.0f}", team_b: "{:.0f}"}),
                                use_container_width=True, hide_index=True
                            )
                    with col_rem:
                        st.subheader("🔮 Projected Remaining")
                        st.caption(f"Expected output today to {end_str} based on **{timeframe}** trends.")
                        df_rem = pd.DataFrame(rem_data)
                        st.dataframe(
                            df_rem.style.highlight_max(subset=[team_a, team_b], color='#2e7b50', axis=1)
                            .format({team_a: "{:.1f}", team_b: "{:.1f}"}),
                            use_container_width=True, hide_index=True
                        )

                    st.subheader("🏆 Final Projected Box Score")
                    st.caption("Current Weekly Score + Projected Remaining")
                    df_final = pd.DataFrame(final_data)
                    st.dataframe(
                        df_final.style.highlight_max(subset=[team_a, team_b], color='#2e7b50', axis=1)
                        .format({team_a: "{:.1f}", team_b: "{:.1f}"}),
                        use_container_width=True, hide_index=True
                    )

        except Exception as e:
            st.warning(f"⚠️ Error in matchup simulator: {e}")
            import traceback; st.code(traceback.format_exc())
