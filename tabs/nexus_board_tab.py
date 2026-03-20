"""
tabs/nexus_board_tab.py — NexusBoard Tab
Composite schedule analyzer: schedule + category value + roster + free agents.
"""

import streamlit as st
import pandas as pd
from nexus_board import build_nexusboard


def render(tab, evaluated_df, g_df_global, cats, weights, season):
    with tab:
        st.header("🗺️ NexusBoard")
        st.caption(
            "Your weekly command center. Schedule, category value, your players, "
            "and top free agents — all in one view."
        )

        yahoo_df = st.session_state.get('yahoo_data', None)

        # ── Controls ──────────────────────────────────────────────────────────
        ctrl1, ctrl2, ctrl3, ctrl4 = st.columns([2, 2, 2, 2])
        with ctrl1:
            week_choice = st.radio(
                "Week", ["This Week", "Next Week", "Remaining", "Playoffs"],
                horizontal=True, key="nb_week"
            )
        with ctrl2:
            sort_by = st.selectbox(
                "Sort by", ["Ease", "GP", "Team", "Off Nights", "My Players First"],
                key="nb_sort"
            )
        with ctrl3:
            show_my   = st.checkbox("Show My Players", value=True, key="nb_mine")
            show_fa   = st.checkbox("Show Top FAs",    value=True, key="nb_fa")
        with ctrl4:
            show_catv = st.checkbox("Show Category Values", value=True, key="nb_catv")
            show_days = st.checkbox("Show Day Grid",        value=True, key="nb_days")

        st.divider()

        # ── Build NexusBoard ──────────────────────────────────────────────────
        with st.spinner("🗺️ Building NexusBoard..."):
            try:
                grid_df, week_info, day_cols = build_nexusboard(
                    week_label   = week_choice,
                    evaluated_df = evaluated_df,
                    g_df_global  = g_df_global,
                    yahoo_df     = yahoo_df,
                    weights      = weights,
                    cats         = cats,
                    season       = season,
                )
            except Exception as e:
                st.error(f"NexusBoard build error: {e}")
                import traceback; st.code(traceback.format_exc())
                return

        if grid_df.empty:
            st.warning("No schedule data available for this period.")
            return

        st.caption(
            f"📅 **{week_info['label']}** &nbsp;|&nbsp; "
            f"{week_info['start']} → {week_info['end']} &nbsp;|&nbsp; "
            f"{len(grid_df)} NHL teams"
        )

        # ── Sorting ───────────────────────────────────────────────────────────
        if sort_by == "GP":
            grid_df = grid_df.sort_values('GP', ascending=False)
        elif sort_by == "Team":
            grid_df = grid_df.sort_values('Team')
        elif sort_by == "Off Nights":
            grid_df = grid_df.sort_values('Off', ascending=False)
        elif sort_by == "My Players First":
            grid_df['_has_mine'] = grid_df['My Players'].apply(lambda x: 0 if x == '—' else 1)
            grid_df = grid_df.sort_values(['_has_mine', 'Ease'], ascending=[False, False])
            grid_df = grid_df.drop(columns=['_has_mine'])
        # default: already sorted by Ease

        # ── Build display columns ─────────────────────────────────────────────
        base_cols  = ['Team', 'GP', 'H', 'A', 'B2B', 'Off', 'Ease']
        cat_v_cols = [f"{c}V" for c in cats if f"{c}V" in grid_df.columns]
        roster_cols = []
        if show_my: roster_cols.append('My Players')
        if show_fa: roster_cols.append('Top FAs')

        display_cols = base_cols.copy()
        if show_days:
            display_cols += [d for d in day_cols if d in grid_df.columns]
        if show_catv:
            display_cols += cat_v_cols
        display_cols += roster_cols

        display_cols = [c for c in display_cols if c in grid_df.columns]
        display_df   = grid_df[display_cols].reset_index(drop=True)

        # ── Styling ───────────────────────────────────────────────────────────
        def ease_color(val):
            try:
                v = float(val)
                if v >= 0.70: return 'background-color:#1a4a2e;color:white;font-weight:700'
                elif v >= 0.55: return 'background-color:#4a3a00;color:white;font-weight:700'
                else: return 'background-color:#4a1a1a;color:white'
            except Exception:
                return ''

        def day_color(val):
            if val == '—': return 'color:#555;background-color:#1a1a1a'
            if str(val).startswith('vs'): return 'background-color:#1a3a2e;color:#7FD9A0'
            if str(val).startswith('@'):  return 'background-color:#1a2a3a;color:#7FB8F0'
            return ''

        def catv_color(val):
            try:
                v = float(val)
                if v > 0.1:  return 'color:#7FD9A0;font-weight:600'
                elif v < -0.1: return 'color:#F5A0A0'
                return ''
            except Exception:
                return ''

        def mine_color(val):
            if val and val != '—':
                return 'background-color:#1a3a2e;color:#7FD9A0'
            return ''

        styled = display_df.style

        if 'Ease' in display_cols:
            styled = styled.applymap(ease_color, subset=['Ease'])

        day_display_cols = [d for d in day_cols if d in display_cols]
        if day_display_cols:
            styled = styled.applymap(day_color, subset=day_display_cols)

        if show_catv and cat_v_cols:
            visible_catv = [c for c in cat_v_cols if c in display_cols]
            if visible_catv:
                styled = styled.applymap(catv_color, subset=visible_catv)

        if show_my and 'My Players' in display_cols:
            styled = styled.applymap(mine_color, subset=['My Players'])

        fmt = {'Ease': '{:.2f}', 'GP': '{:.0f}', 'H': '{:.0f}', 'A': '{:.0f}',
               'B2B': '{:.0f}', 'Off': '{:.0f}'}
        for c in cat_v_cols:
            if c in display_cols:
                fmt[c] = '{:+.2f}'
        styled = styled.format(fmt, na_rep='—')

        # ── Rename day columns to short day names for readability ──────────────
        day_rename = {}
        for d_str in day_display_cols:
            try:
                dt = pd.Timestamp(d_str)
                day_rename[d_str] = dt.strftime('%a %-d') if hasattr(dt, 'strftime') else d_str
            except Exception:
                day_rename[d_str] = d_str

        # Rename cat value columns for display
        catv_rename = {f"{c}V": f"{c} Val" for c in cats}
        all_rename = {**day_rename, **catv_rename}
        styled = styled.set_table_attributes('style="font-size:12.5px"')

        # Column widths
        col_cfg = {
            'Team': st.column_config.TextColumn('Team', width=55),
            'GP':   st.column_config.NumberColumn('GP',  width=40),
            'H':    st.column_config.NumberColumn('H',   width=35),
            'A':    st.column_config.NumberColumn('A',   width=35),
            'B2B':  st.column_config.NumberColumn('B2B', width=40),
            'Off':  st.column_config.NumberColumn('⭐Off', width=45),
            'Ease': st.column_config.NumberColumn('Ease', width=55, format='%.2f'),
            'My Players': st.column_config.TextColumn('🟩 My Players', width=180),
            'Top FAs':    st.column_config.TextColumn('💎 Top FAs',    width=220),
        }
        for d_str in day_display_cols:
            short = day_rename.get(d_str, d_str)
            col_cfg[d_str] = st.column_config.TextColumn(short, width=60)
        for c in cats:
            if f"{c}V" in display_cols:
                col_cfg[f"{c}V"] = st.column_config.NumberColumn(f"{c}↑", width=50, format='%+.2f')

        st.dataframe(
            styled,
            hide_index=True,
            use_container_width=True,
            height=min(80 + len(display_df) * 36, 900),
            column_config=col_cfg,
        )

        # ── Legend ────────────────────────────────────────────────────────────
        st.caption(
            "🟢 Home game &nbsp;|&nbsp; 🔵 Away game &nbsp;|&nbsp; "
            "Ease: 0–1 composite (game count, home%, opponent quality, B2B) &nbsp;|&nbsp; "
            "⭐ Off = off-night games (Mon/Wed/Fri/Sun) &nbsp;|&nbsp; "
            "Cat Val = schedule value vs average opponent"
        )

        # ── No sync warning ───────────────────────────────────────────────────
        if yahoo_df is None:
            st.info(
                "💡 Sync your Yahoo or ESPN league to see **My Players** "
                "and **Top FAs** for each team."
            )
