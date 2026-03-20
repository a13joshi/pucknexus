import streamlit as st
from goalie_intel import (
    get_todays_goalies, calculate_sos_score,
    get_goalie_streaming_ranks, GOALIE_RESOURCES
)


def render(tab, g_df_global):
    with tab:
        st.header("🥅 Goalie Intelligence Engine")
        st.caption("Tonight's starters (confirmed, probable, or projected), Strength of Start scores, and streaming rankings.")

        try:
            st.markdown(
                "**📡 Early Goalie Reports (human-confirmed):** " +
                " &nbsp;|&nbsp; ".join(f"[{r['name']}]({r['url']})" for r in GOALIE_RESOURCES)
            )
            st.caption("These sites post goalie confirmations from practice reports — usually 2–3 hours before puck drop.")
            st.divider()

            col_l, col_r = st.columns(2)

            with col_l:
                st.subheader("🏒 Tonight's Starters")
                if st.button("🔄 Refresh Goalie Status", use_container_width=True):
                    st.session_state['today_goalies'] = get_todays_goalies(season_goalie_df=g_df_global)

                if 'today_goalies' not in st.session_state:
                    with st.spinner("Loading tonight's goalies..."):
                        st.session_state['today_goalies'] = get_todays_goalies(season_goalie_df=g_df_global)

                tg = st.session_state['today_goalies']

                if not tg.empty:
                    n_confirmed = len(tg[tg['Status'] == 'Confirmed'])
                    n_probable  = len(tg[tg['Status'] == 'Probable'])
                    n_projected = len(tg[tg['Status'].isin(['Projected', 'TBD'])])
                    s1, s2, s3 = st.columns(3)
                    s1.metric("✅ Confirmed",  n_confirmed)
                    s2.metric("📋 Probable",   n_probable)
                    s3.metric("📊 Projected",  n_projected)

                    def status_color(val):
                        if val == 'Confirmed':  return 'background-color:#1a4a2e;color:white'
                        elif val == 'Probable': return 'background-color:#1a3a5c;color:white'
                        elif val == 'Projected': return 'background-color:#4a3a00;color:white'
                        else: return 'background-color:#4a1a1a;color:white'

                    display_cols = [c for c in ['GoalieName', 'Team', 'Opponent', 'Home', 'Status', 'Note', 'GameTime'] if c in tg.columns]
                    tg_d = tg[display_cols].copy()
                    if 'Home' in tg_d.columns:
                        tg_d['Home'] = tg_d['Home'].apply(lambda x: '🏠' if x else '✈️')
                    if 'GameTime' in tg_d.columns:
                        tg_d['GameTime'] = tg_d['GameTime'].apply(
                            lambda x: x[11:16] + ' UTC' if isinstance(x, str) and len(x) > 10 else x
                        )
                    st.dataframe(tg_d.style.applymap(status_color, subset=['Status']),
                                 hide_index=True, use_container_width=True)
                else:
                    st.info("No games today or goalie data unavailable.")

            with col_r:
                st.subheader("📊 Strength of Start (SoS)")
                st.caption("0–100 composite: 40% form, 20% home, 25% opponent, 15% rest.")

                if not tg.empty and not g_df_global.empty:
                    scored = calculate_sos_score(tg, g_df_global)
                    if not scored.empty:
                        sos_cols = [c for c in ['GoalieName', 'Team', 'Opponent', 'Home', 'SoS', 'Grade', 'SV%', 'W', 'GAA'] if c in scored.columns]
                        sos_d = scored[sos_cols].copy()
                        if 'Home' in sos_d.columns:
                            sos_d['Home'] = sos_d['Home'].apply(lambda x: '🏠' if x else '✈️')
                        st.dataframe(
                            sos_d.style.background_gradient(cmap='RdYlGn', subset=['SoS'])
                            .format({'SoS': '{:.1f}', 'SV%': '{:.3f}', 'GAA': '{:.2f}'}),
                            hide_index=True, use_container_width=True
                        )
                else:
                    st.info("Run a sync or wait for goalie data to load.")

            st.divider()
            st.subheader("🎯 Goalie Streaming Rankings — Top 20")
            st.caption("Best free-agent streaming options: SV% (60%) + win rate (40%).")

            if not g_df_global.empty:
                if 'yahoo_data' in st.session_state:
                    yahoo_d = st.session_state['yahoo_data']
                    fa_names = set(
                        yahoo_d[yahoo_d['Status'] == 'Free Agent']['match_key'].tolist()
                    ) if 'match_key' in yahoo_d.columns else set(
                        yahoo_d[yahoo_d['Status'] == 'Free Agent']['name'].str.lower().str.strip().tolist()
                    )
                    fa_goalies = g_df_global[g_df_global['Player'].str.lower().str.strip().isin(fa_names)]
                    if fa_goalies.empty:
                        st.caption("⚠️ No free agent goalies found — showing all.")
                        fa_goalies = g_df_global
                    else:
                        st.caption(f"Showing {len(fa_goalies)} free agent goalies in your league.")
                else:
                    fa_goalies = g_df_global
                    st.caption("⚠️ Sync your league to filter to free agents only.")

                stream_df = get_goalie_streaming_ranks(fa_goalies)
                if not stream_df.empty:
                    st.dataframe(
                        stream_df.style.background_gradient(cmap='RdYlGn', subset=['StreamScore'])
                        .format({'StreamScore': '{:.1f}', 'SV%': '{:.3f}', 'GAA': '{:.2f}'}),
                        hide_index=True, use_container_width=True, height=600
                    )
            else:
                st.info("Goalie data not loaded yet.")

        except Exception as e:
            st.error(f"Goalie Intel error: {e}")
            import traceback; st.code(traceback.format_exc())
