import streamlit as st
import plotly.express as px


def render(tab, evaluated_df, evaluated_goalies, cats, weights):
    with tab:
        st.header("🏆 League Power Rankings")
        try:
            if 'yahoo_data' not in st.session_state:
                st.info("Sync your Yahoo or ESPN league in the Control Center above.")
                return

            yahoo_df = st.session_state['yahoo_data']

            active_cats = [c for c in cats if weights[c] > 0]
            s_cat_cols  = [f"{c}V" for c in active_cats]
            g_cat_cols  = ['WV', 'GAAV', 'SV%V', 'SHOV']

            s_cols = ['match_key', 'NexusScore'] + [c for c in s_cat_cols if c in evaluated_df.columns]
            g_cols = ['match_key', 'NexusScore'] + [c for c in g_cat_cols if c in evaluated_goalies.columns]

            skater_league = evaluated_df[s_cols].pipe(lambda d: d.merge(yahoo_df, on='match_key', how='inner')) \
                if not evaluated_df.empty else None
            goalie_league = evaluated_goalies[g_cols].pipe(lambda d: d.merge(yahoo_df, on='match_key', how='inner')) \
                if not evaluated_goalies.empty else None

            import pandas as pd
            parts = [df for df in [skater_league, goalie_league] if df is not None]
            if not parts:
                st.warning("No data to display.")
                return

            full_league_df = pd.concat(parts).fillna(0)
            rostered_df    = full_league_df[full_league_df['Status'] == 'Rostered']

            all_cat_cols = [c for c in s_cat_cols + g_cat_cols if c in rostered_df.columns]
            team_power   = (
                rostered_df.groupby(['Fantasy_Team', 'Manager'])[['NexusScore'] + all_cat_cols]
                .sum().reset_index()
                .sort_values(by='NexusScore', ascending=True)
            )

            st.subheader("⚡ True Team Power (Skaters + Goalies)")
            fig1 = px.bar(team_power, x='NexusScore', y='Fantasy_Team', orientation='h',
                         color='NexusScore', color_continuous_scale='viridis', text_auto='.2f')
            fig1.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig1, use_container_width=True)

            st.divider()
            st.subheader("🧬 Category Dominance Breakdown")
            st.caption("Hover over segments to see where teams gain or lose value.")
            fig2 = px.bar(team_power, x=all_cat_cols, y='Fantasy_Team', orientation='h',
                         labels={'value': 'Total NexusScore', 'variable': 'Category'})
            fig2.update_layout(height=600, barmode='relative', legend_title_text='Categories')
            st.plotly_chart(fig2, use_container_width=True)

        except Exception as e:
            st.warning(f"⚠️ No league data found. Sync your league. ({e})")
