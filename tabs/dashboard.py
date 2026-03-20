import streamlit as st
import pandas as pd
import unicodedata
from config import get_team_logo, get_headshot


def render(tab, final, evaluated_df, evaluated_goalies, cats, g_cats,
           weights, selected_pos, num_teams=12):
    with tab:
        if not evaluated_goalies.empty and 'Pos' not in evaluated_goalies.columns:
            evaluated_goalies['Pos'] = 'G'

        if not evaluated_df.empty and not evaluated_goalies.empty:
            df = pd.concat([evaluated_df, evaluated_goalies], ignore_index=True)
        elif not evaluated_df.empty:
            df = evaluated_df.copy()
        elif not evaluated_goalies.empty:
            df = evaluated_goalies.copy()
        else:
            st.error("No data available.")
            return

        df = df.sort_values('GP', ascending=True).drop_duplicates('Player', keep='last')

        # VORP baselines
        baselines = {}
        for pos in ['C', 'L', 'R', 'D', 'G']:
            pos_players = df[df['Pos'].str.contains(pos, na=False)].sort_values('NexusScore', ascending=False)
            rep_idx = 48 if pos == 'D' else (24 if pos == 'G' else 36)
            if len(pos_players) > rep_idx:
                baselines[pos] = pos_players.iloc[rep_idx]['NexusScore']
            elif len(pos_players) > 0:
                baselines[pos] = pos_players.iloc[-1]['NexusScore']
            else:
                baselines[pos] = 0

        def calculate_vorp(row):
            if pd.isna(row['Pos']): return 0.0
            primary_pos = str(row['Pos']).replace('/', ',').split(',')[0].strip()
            return row['NexusScore'] - baselines.get(primary_pos, 0.0)

        df['VORP'] = df.apply(calculate_vorp, axis=1)

        def clean_name(name):
            if pd.isna(name): return ""
            return unicodedata.normalize('NFKD', str(name)).encode('ASCII', 'ignore').decode('utf-8').lower().strip()

        actual_num_teams = num_teams
        try:
            if 'yahoo_data' in st.session_state:
                y_data = st.session_state['yahoo_data'].copy()
                y_data['match_key'] = y_data['name'].apply(clean_name)
                actual_teams = y_data['Fantasy_Team'].nunique()
                if actual_teams > 0:
                    actual_num_teams = actual_teams
                own_map = y_data[['match_key', 'Status', 'Is_Mine']].drop_duplicates('match_key')
                def determine_own(row):
                    if row.get('Is_Mine') == True: return "Mine"
                    if row.get('Status') == 'Rostered': return "Taken"
                    return "FA"
                own_map['Own'] = own_map.apply(determine_own, axis=1)
                df['match_key'] = df['Player'].apply(clean_name)
                df = pd.merge(df, own_map[['match_key', 'Own']], on='match_key', how='left')
                df['Own'] = df['Own'].fillna("FA")
            else:
                df['Own'] = "FA"
        except Exception:
            df['Own'] = "FA"

        st.markdown("### 🎯 Unified Player Value Dashboard")

        if 'yahoo_data' in st.session_state:
            view_mode = st.radio("View", ["🏒 League Pool", "🌐 Full NHL"], horizontal=True, label_visibility="collapsed")
        else:
            view_mode = "🌐 Full NHL"
            st.caption("💡 Sync your Yahoo/ESPN league to enable League Pool view.")

        if view_mode == "🏒 League Pool" and 'yahoo_data' in st.session_state:
            league_players = st.session_state['yahoo_data']['name'].str.lower().str.strip().tolist()
            df = df[df['Player'].str.lower().str.strip().isin(league_players)]

        st.caption(f"Players sorted by **NexusScore**. 🟩 = Your Roster | ⬛ = Taken | Blank = Free Agent. (Separator lines every {actual_num_teams} players).")

        if 'Pos' in df.columns:
            df = df[df['Pos'].isin(selected_pos)]
        df = df.sort_values(by="NexusScore", ascending=False)

        if 'Team' in df.columns: df['Logo'] = df['Team'].apply(get_team_logo)
        if 'playerId' in df.columns: df['Headshot'] = df.apply(get_headshot, axis=1)

        display_df = df.copy()
        display_df['Rank'] = range(1, len(display_df) + 1)
        if 'Team' in display_df.columns:
            display_df = display_df.rename(columns={'Team': 'NHL Team'})

        g_cats_display = ['W', 'GAA', 'SV%', 'SHO']
        cols_order = ['Own', 'Rank', 'Headshot', 'NHL Team', 'Logo', 'Player', 'Pos', 'VORP', 'NexusScore', 'GP'] + cats + g_cats_display
        actual_cols = [c for c in cols_order if c in display_df.columns]

        def base_style(val):
            if pd.isna(val):
                return 'background-color: #1c1f26; color: transparent; border: none;'
            return 'background-color: #0e1117; color: #ffffff;'

        styled = display_df[actual_cols].style.map(base_style)

        left_cols = ['Rank', 'Headshot', 'NHL Team', 'Logo', 'Player', 'Pos']
        styled = styled.map(
            lambda x: 'background-color: #2A303C; color: #ffffff;' if not pd.isna(x) else 'background-color: #1c1f26;',
            subset=[c for c in left_cols if c in actual_cols]
        )
        styled = styled.map(
            lambda x: 'background-color: #1c1f26; color: #ffffff; font-weight: bold;' if not pd.isna(x) else 'background-color: #1c1f26;',
            subset=['GP']
        )
        styled = styled.map(
            lambda x: 'background-color: #00CC96; color: transparent;' if x == 'Mine'
            else ('background-color: #333333; color: transparent;' if x == 'Taken' else 'background-color: #2A303C;'),
            subset=['Own']
        )

        fmt_dict = {'NexusScore': "{:.2f}", 'VORP': "{:.2f}", 'GP': "{:.0f}", 'GAA': "{:.2f}", 'SV%': "{:.3f}", 'W': "{:.0f}", 'SHO': "{:.0f}"}
        for c in cats: fmt_dict[c] = "{:.0f}"
        styled = styled.format(formatter=fmt_dict, na_rep="")

        for c in ['NexusScore'] + cats + ['W', 'SV%', 'SHO']:
            if c in display_df.columns:
                q_min = display_df[c].quantile(0.05)
                q_max = display_df[c].max()
                if pd.notna(q_min) and pd.notna(q_max) and q_min != q_max:
                    styled = styled.background_gradient(cmap="RdYlGn", subset=[c], vmin=q_min, vmax=q_max, text_color_threshold=0.5)

        if 'GAA' in display_df.columns:
            q_min = display_df['GAA'].min()
            q_max = display_df['GAA'].quantile(0.95)
            if pd.notna(q_min) and pd.notna(q_max) and q_min != q_max:
                styled = styled.background_gradient(cmap="RdYlGn_r", subset=['GAA'], vmin=q_min, vmax=q_max, text_color_threshold=0.5)

        def round_separators(row):
            return [('border-bottom: 4px solid #556070 !important;' if row['Rank'] % actual_num_teams == 0 else '') for _ in row.index]

        styled = styled.apply(round_separators, axis=1)

        cfg = {
            "Own": st.column_config.Column("", width=30),
            "Rank": st.column_config.NumberColumn("Rnk", width=40),
            "Headshot": st.column_config.ImageColumn("", width=35),
            "NHL Team": st.column_config.Column("Team", width=45),
            "Logo": st.column_config.ImageColumn("", width=35),
            "Player": st.column_config.Column("Player", width=150),
            "Pos": st.column_config.Column("Pos", width=40),
            "VORP": st.column_config.ProgressColumn("Scarcity", format="%.2f", min_value=-2.0, max_value=4.0, width=90),
            "NexusScore": st.column_config.Column("NexusScore", width=75),
            "GP": st.column_config.Column("GP", width=60),
            "W": st.column_config.Column("W", width=60),
            "GAA": st.column_config.Column("GAA", width=65),
            "SV%": st.column_config.Column("SV%", width=65),
            "SHO": st.column_config.Column("SHO", width=60),
        }
        for c in cats:
            cfg[c] = st.column_config.Column(c, width=65)

        st.dataframe(styled, height=800, column_config=cfg, hide_index=True, use_container_width=False)
