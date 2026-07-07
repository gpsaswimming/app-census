"""
Alignment Analysis

Multi-season division alignment analysis: team performance history, weighted
scoring, movement recommendations, and Streamlit rendering.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import func, distinct
from sqlalchemy.orm import Session

from db.models import Team, Meet, MeetTeam, Event, Result
from dashboard.utils.division_config import DivisionConfigManager


# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------

def get_season_team_data(session: Session, season: str) -> pd.DataFrame | None:
    """Return a DataFrame of team performance metrics for one season.

    Columns: team_id, Team, Code, Roster Size, Division, W, L, Pts For,
    Pts Against, Pt Diff, Meets, Avg Diff, CM Points, CM Finish, Season
    """
    division_manager = DivisionConfigManager(session)

    team_roster_data = session.query(
        Team.id.label('team_id'),
        Team.name.label('team_name'),
        Team.code.label('team_code'),
        func.count(distinct(Result.athlete_id)).label('roster_size')
    ).select_from(Team).join(
        Result, Team.id == Result.team_id
    ).join(
        Event, Result.event_id == Event.id
    ).join(
        Meet, Event.meet_id == Meet.id
    ).filter(
        Meet.date.isnot(None),
        Meet.date.like(f'{season}%')
    ).group_by(Team.id, Team.name, Team.code).all()

    if not team_roster_data:
        return None

    df = pd.DataFrame(team_roster_data, columns=['team_id', 'Team', 'Code', 'Roster Size'])

    divisions = division_manager.get_divisions_for_season(int(season))
    division_lookup = {}
    for div_name in ['red', 'white', 'blue']:
        for team in divisions[div_name]:
            division_lookup[team['id']] = div_name
    df['Division'] = df['team_id'].map(division_lookup).fillna('—')

    dual_meets = session.query(Meet).filter(
        Meet.meet_type == 'dual',
        Meet.date.like(f'{season}%')
    ).all()

    team_records = {}
    team_points_for = {}
    team_points_against = {}

    for meet in dual_meets:
        meet_teams = session.query(
            MeetTeam.team_id,
            MeetTeam.score
        ).filter(MeetTeam.meet_id == meet.id).all()

        if len(meet_teams) == 2:
            team1_id, score1 = meet_teams[0]
            team2_id, score2 = meet_teams[1]

            if score1 is not None and score2 is not None:
                for tid in [team1_id, team2_id]:
                    if tid not in team_records:
                        team_records[tid] = {'W': 0, 'L': 0}
                        team_points_for[tid] = 0
                        team_points_against[tid] = 0

                team_points_for[team1_id] += score1
                team_points_against[team1_id] += score2
                team_points_for[team2_id] += score2
                team_points_against[team2_id] += score1

                if score1 > score2:
                    team_records[team1_id]['W'] += 1
                    team_records[team2_id]['L'] += 1
                elif score2 > score1:
                    team_records[team2_id]['W'] += 1
                    team_records[team1_id]['L'] += 1

    df['W'] = df['team_id'].map(lambda x: team_records.get(x, {}).get('W', 0))
    df['L'] = df['team_id'].map(lambda x: team_records.get(x, {}).get('L', 0))
    df['Pts For'] = df['team_id'].map(lambda x: team_points_for.get(x, 0))
    df['Pts Against'] = df['team_id'].map(lambda x: team_points_against.get(x, 0))
    df['Pt Diff'] = df['Pts For'] - df['Pts Against']
    df['Meets'] = df['W'] + df['L']
    df['Avg Diff'] = df.apply(
        lambda r: round(r['Pt Diff'] / r['Meets'], 1) if r['Meets'] > 0 else 0, axis=1
    )

    city_meet = session.query(Meet).filter(
        Meet.meet_type == 'city_meet',
        Meet.date.like(f'{season}%')
    ).first()

    city_meet_points = {}
    city_meet_finish = {}
    if city_meet:
        city_meet_teams = session.query(
            MeetTeam.team_id,
            MeetTeam.score
        ).filter(MeetTeam.meet_id == city_meet.id).all()

        sorted_teams = sorted(
            city_meet_teams, key=lambda x: x.score if x.score else 0, reverse=True
        )
        for idx, (team_id, score) in enumerate(sorted_teams, 1):
            city_meet_points[team_id] = score or 0
            city_meet_finish[team_id] = idx

    df['CM Points'] = df['team_id'].map(city_meet_points).fillna(0).astype(int)
    df['CM Finish'] = df['team_id'].map(city_meet_finish)
    df['Season'] = season

    return df


# ---------------------------------------------------------------------------
# Recommendation logic
# ---------------------------------------------------------------------------

# Scoring weights
_WEIGHT_AVG_DIFF = 0.65
_WEIGHT_PT_DIFF = 0.35
_STRONG_THRESHOLD = 120
_MODERATE_THRESHOLD = 75


def _compute_season_weights(n: int) -> dict:
    """Return index→weight mapping that sums to 1.0 for n lookback seasons.

    Preserves calibrated values for n <= 3; for larger n uses geometric decay.
    """
    if n == 1:
        return {0: 1.0}
    if n == 2:
        return {0: 0.60, 1: 0.40}
    if n == 3:
        return {0: 0.50, 1: 0.33, 2: 0.17}
    # n > 3: geometric decay 2^(n-1-i), normalized
    raw = [2 ** (n - 1 - i) for i in range(n)]
    total = sum(raw)
    return {i: round(raw[i] / total, 4) for i in range(n)}


def _compute_recommendation(
    team_id: int,
    team_history: dict,
    stabilization_years: int = 2,
    dominant_override: int = 200,
) -> tuple[str, str, str]:
    """Return (flag, trend, reason) for one team given its multi-season history dict."""
    hist = team_history.get(team_id, {})
    if not hist.get('pt_diff_vs_div_avg'):
        return '', '', 'Insufficient data'

    pt_diffs_vs_avg = hist['pt_diff_vs_div_avg']
    avg_diffs_vs_avg = hist['avg_diff_vs_div_avg']
    divisions = hist['divisions']
    seasons = hist['seasons']
    div_changes = hist['division_changes']
    current_div = divisions[0] if divisions else '—'

    # Only consider consecutive years in the current division
    consecutive_indices = []
    for i, div in enumerate(divisions):
        if div == current_div:
            consecutive_indices.append(i)
        else:
            break

    filtered_pt_diffs = [pt_diffs_vs_avg[i] for i in consecutive_indices]
    filtered_avg_diffs = [avg_diffs_vs_avg[i] for i in consecutive_indices]
    filtered_seasons = [seasons[i] for i in consecutive_indices]
    years_in_division = len(consecutive_indices)

    recently_moved = 0 < years_in_division < stabilization_years
    move_direction = move_from = move_to = move_season = None

    if recently_moved and consecutive_indices:
        for change in div_changes:
            if change['to'] == current_div:
                move_from = change['from']
                move_to = change['to']
                move_season = change['season']
                div_order = {'blue': 0, 'white': 1, 'red': 2}
                move_direction = (
                    'up' if div_order.get(change['to'], 0) > div_order.get(change['from'], 0)
                    else 'down'
                )
                break

    # Weighted score over consecutive years
    weighted_pt_score = 0.0
    weighted_avg_score = 0.0
    if filtered_pt_diffs:
        weights = _compute_season_weights(len(filtered_pt_diffs))
        for i in range(len(filtered_pt_diffs)):
            w = weights[i]
            weighted_pt_score += filtered_pt_diffs[i] * w
            weighted_avg_score += filtered_avg_diffs[i] * w

    avg_diff_scaled = weighted_avg_score * 4
    base_score = (_WEIGHT_AVG_DIFF * avg_diff_scaled) + (_WEIGHT_PT_DIFF * weighted_pt_score)

    # Trend detection
    trend = ''
    trend_factor = 0.0
    if len(filtered_avg_diffs) >= 2:
        recent_change = filtered_avg_diffs[0] - filtered_avg_diffs[1]
        if len(filtered_avg_diffs) >= 3:
            older_change = filtered_avg_diffs[1] - filtered_avg_diffs[2]
            total_change = filtered_avg_diffs[0] - filtered_avg_diffs[-1]
            if recent_change > 10 and older_change > 10:
                trend = '📈'
                trend_factor = abs(total_change) * 2
            elif recent_change < -10 and older_change < -10:
                trend = '📉'
                trend_factor = -abs(total_change) * 2
            elif total_change > 20:
                trend = '📈'
                trend_factor = total_change
            elif total_change < -20:
                trend = '📉'
                trend_factor = total_change
        else:
            if recent_change > 15:
                trend = '📈'
                trend_factor = recent_change
            elif recent_change < -15:
                trend = '📉'
                trend_factor = recent_change

    weighted_score = base_score + trend_factor

    seasons_above = sum(1 for x in filtered_pt_diffs if x > _MODERATE_THRESHOLD)
    seasons_below = sum(1 for x in filtered_pt_diffs if x < -_MODERATE_THRESHOLD)
    yr_str = f"{years_in_division}yr" if years_in_division > 0 else ""

    flag = ''
    reason = ''

    if recently_moved:
        from_cap = move_from.capitalize() if move_from else ''
        to_cap = move_to.capitalize() if move_to else ''
        if move_direction == 'up' and weighted_score < -_MODERATE_THRESHOLD:
            flag = '🔄'
            reason = f'Moved up ({from_cap}→{to_cap} in {move_season}), adjusting ({yr_str} data)'
        elif move_direction == 'up' and weighted_score > _MODERATE_THRESHOLD:
            flag = '✓'
            reason = f'Moved up ({from_cap}→{to_cap} in {move_season}), thriving ({yr_str} data)'
        elif move_direction == 'down' and weighted_score > _MODERATE_THRESHOLD:
            flag = '⬆️'
            reason = f'Moved down ({from_cap}→{to_cap} in {move_season}) but dominating - consider moving back'
        elif move_direction == 'down' and weighted_score < -_MODERATE_THRESHOLD:
            flag = '✓'
            reason = f'Moved down ({from_cap}→{to_cap} in {move_season}), finding footing ({yr_str} data)'
        else:
            flag = '🔄'
            reason = f'Moved ({from_cap}→{to_cap} in {move_season}), monitoring ({yr_str} data)'
    elif current_div == 'red':
        if weighted_score < -_STRONG_THRESHOLD and seasons_below >= 2:
            if trend == '📈':
                flag = '📈'
                reason = f'Struggled but improving - monitor ({yr_str} data)'
            else:
                flag = '⬇️'
                reason = f'Struggled in Red {seasons_below}/{years_in_division} yrs (score: {weighted_score:+.0f})'
        elif trend == '📉':
            flag = '📉'
            reason = f'Declining trend in Red ({yr_str} data)'
        elif weighted_score > _STRONG_THRESHOLD:
            flag = '✓'
            reason = f'Strong Red team ({yr_str} data)'
    elif current_div == 'blue':
        if weighted_score > _STRONG_THRESHOLD and seasons_above >= 2:
            if trend == '📉' and weighted_score < dominant_override:
                flag = '📉'
                reason = f'Strong but declining - not ready to move up ({yr_str} data)'
            elif trend == '📉':
                flag = '⬆️'
                reason = f'Dominating Blue despite decline - consider moving up ({yr_str} data)'
            else:
                flag = '⬆️'
                reason = f'Dominated Blue {seasons_above}/{years_in_division} yrs (score: {weighted_score:+.0f})'
        elif trend == '📈':
            flag = '📈'
            reason = f'Rising in Blue ({yr_str} data)'
        elif weighted_score < -_STRONG_THRESHOLD:
            flag = '✓'
            reason = f'Appropriately placed in Blue ({yr_str} data)'
    elif current_div == 'white':
        if weighted_score > _STRONG_THRESHOLD and seasons_above >= 2:
            if trend == '📉' and weighted_score < dominant_override:
                flag = '📉'
                reason = f'Strong but declining - not ready to move up ({yr_str} data)'
            elif trend == '📉':
                flag = '⬆️'
                reason = f'Dominating White despite decline - consider moving up ({yr_str} data)'
            else:
                flag = '⬆️'
                reason = f'Dominated White {seasons_above}/{years_in_division} yrs (score: {weighted_score:+.0f})'
        elif weighted_score < -_STRONG_THRESHOLD and seasons_below >= 2:
            if trend == '📈':
                flag = '📈'
                reason = f'Struggled but improving - monitor ({yr_str} data)'
            else:
                flag = '⬇️'
                reason = f'Struggled in White {seasons_below}/{years_in_division} yrs (score: {weighted_score:+.0f})'
        elif trend == '📈':
            flag = '📈'
            reason = f'Rising in White ({yr_str} data)'
        elif trend == '📉':
            flag = '📉'
            reason = f'Declining in White ({yr_str} data)'

    if not flag:
        flag = '✓'
        reason = f'Well placed ({yr_str} in {current_div.capitalize() if current_div != "—" else "division"})'

    return flag, trend, reason


# ---------------------------------------------------------------------------
# Streamlit rendering
# ---------------------------------------------------------------------------

_DIVISION_INFO = {
    'red':   {'emoji': '🔴', 'name': 'Red Division',   'desc': 'Top competitive division'},
    'white': {'emoji': '⚪', 'name': 'White Division',  'desc': 'Middle division'},
    'blue':  {'emoji': '🔵', 'name': 'Blue Division',   'desc': 'Development division'},
}

_AGE_GROUPS = ['8 & Under', '9-10', '11-12', '13-14', '15-18']


def render_alignment_analysis(session: Session) -> None:
    """Render the full Alignment Analysis tab in Streamlit."""
    st.header("Alignment Analysis")
    st.markdown("*Multi-season analysis to help balance divisions for competitive fairness.*")

    # All completed seasons in the database
    all_seasons_in_db = sorted(
        list(set([
            m.date[:4]
            for m in session.query(Meet.date).filter(Meet.date.isnot(None)).all()
            if m.date
        ])),
        reverse=True
    )

    if not all_seasons_in_db:
        st.info("No meet data available.")
        return

    max_completed = int(all_seasons_in_db[0])

    # ── Inline controls ───────────────────────────────────────────────────────
    ctl1, ctl2, ctl3, ctl4 = st.columns(4)
    with ctl1:
        planning_season_options = [max_completed + 1] + [int(s) for s in all_seasons_in_db]
        planning_season = st.selectbox(
            "Planning Season",
            options=planning_season_options,
            index=0,
            help="The upcoming season you are planning divisions for."
        )
    with ctl2:
        lookback = st.slider("Lookback Seasons", min_value=2, max_value=5, value=3)
    with ctl3:
        if lookback > 2:
            stabilization_years = st.slider(
                "Stabilization Period",
                min_value=1,
                max_value=lookback - 1,
                value=min(2, lookback - 1),
                help="Seasons in new division before normal recommendations apply."
            )
        else:
            stabilization_years = 1
            st.markdown("**Stabilization Period**")
            st.write("1 *(fixed when Lookback = 2)*")
    with ctl4:
        dominant_override = st.slider(
            "Dominant Override",
            min_value=130,
            max_value=400,
            value=200,
            step=10,
            help=(
                "Weighted score above which a declining team still gets a move-up "
                "recommendation. Set higher to be more conservative."
            )
        )

    # N completed seasons strictly before the planning season
    all_season_strs = sorted(
        [s for s in all_seasons_in_db if int(s) < planning_season],
        reverse=True
    )[:lookback]

    if not all_season_strs:
        st.info("No completed seasons found before the planning season.")
        return

    reference_season = all_season_strs[0]

    # ── Gather multi-season data ──────────────────────────────────────────────
    all_season_data = {}
    for season in all_season_strs:
        df = get_season_team_data(session, season)
        if df is not None:
            all_season_data[season] = df

    if reference_season not in all_season_data:
        st.info("No team data available for the reference season.")
        return

    df_current = all_season_data[reference_season].copy()

    # Division averages for current season
    division_stats = {}
    for div in ['red', 'white', 'blue']:
        div_teams = df_current[df_current['Division'] == div]
        if len(div_teams) > 0:
            division_stats[div] = {
                'avg_pt_diff': div_teams['Pt Diff'].mean(),
                'std_pt_diff': div_teams['Pt Diff'].std() if len(div_teams) > 1 else 0,
                'avg_avg_diff': div_teams['Avg Diff'].mean(),
                'std_avg_diff': div_teams['Avg Diff'].std() if len(div_teams) > 1 else 0,
            }

    # Build historical performance per team
    team_history = {}
    for team_id in df_current['team_id'].unique():
        team_history[team_id] = {
            'seasons': [], 'divisions': [], 'pt_diffs': [], 'avg_diffs': [],
            'pt_diff_vs_div_avg': [], 'avg_diff_vs_div_avg': [], 'division_changes': [],
        }

        prev_division = None
        prev_season = None
        for i, season in enumerate(all_season_strs):
            if season not in all_season_data:
                continue
            df_season = all_season_data[season]
            team_row = df_season[df_season['team_id'] == team_id]
            if len(team_row) == 0:
                continue

            team_row = team_row.iloc[0]
            div = team_row['Division']
            pt_diff = team_row['Pt Diff']
            avg_diff = team_row['Avg Diff']

            div_teams = df_season[df_season['Division'] == div]
            div_avg_pt = div_teams['Pt Diff'].mean() if len(div_teams) > 0 else 0
            div_avg_avg = div_teams['Avg Diff'].mean() if len(div_teams) > 0 else 0

            team_history[team_id]['seasons'].append(season)
            team_history[team_id]['divisions'].append(div)
            team_history[team_id]['pt_diffs'].append(pt_diff)
            team_history[team_id]['avg_diffs'].append(avg_diff)
            team_history[team_id]['pt_diff_vs_div_avg'].append(pt_diff - div_avg_pt)
            team_history[team_id]['avg_diff_vs_div_avg'].append(avg_diff - div_avg_avg)

            if prev_division and div != prev_division and div != '—' and prev_division != '—':
                team_history[team_id]['division_changes'].append({
                    'from': div, 'to': prev_division, 'season': prev_season
                })
            prev_division = div
            prev_season = season

    # Apply recommendations
    df_current['Flag'], df_current['Trend'], df_current['Reason'] = zip(
        *df_current['team_id'].map(
            lambda tid: _compute_recommendation(tid, team_history, stabilization_years, dominant_override)
        )
    )

    # Append historical columns
    for season in all_season_strs:
        if season in all_season_data:
            s_data = all_season_data[season].set_index('team_id')
            df_current[f"PtDiff {season}"] = df_current['team_id'].map(s_data['Pt Diff'].to_dict())
            df_current[f"AvgDiff {season}"] = df_current['team_id'].map(s_data['Avg Diff'].to_dict())
            df_current[f"Div {season}"] = df_current['team_id'].map(s_data['Division'].to_dict())

    # Age group distribution
    age_group_data = session.query(
        Team.id.label('team_id'),
        Event.age_group,
        func.count(distinct(Result.athlete_id)).label('count')
    ).select_from(Result).join(
        Event, Result.event_id == Event.id
    ).join(
        Team, Result.team_id == Team.id
    ).join(
        Meet, Event.meet_id == Meet.id
    ).filter(
        Meet.date.like(f'{reference_season}%'),
        Event.age_group.in_(_AGE_GROUPS)
    ).group_by(Team.id, Event.age_group).all()

    age_group_map = {tid: {ag: 0 for ag in _AGE_GROUPS} for tid in df_current['team_id']}
    for team_id, age_group, count in age_group_data:
        if team_id in age_group_map and age_group in age_group_map[team_id]:
            age_group_map[team_id][age_group] = count
    for ag in _AGE_GROUPS:
        df_current[ag] = df_current['team_id'].map(
            lambda x, ag=ag: age_group_map.get(x, {}).get(ag, 0)
        )

    # ── Sub-tabs ──────────────────────────────────────────────────────────────
    subtab_overview, subtab_red, subtab_white, subtab_blue = st.tabs([
        "📋 Overview", "🔴 Red Division", "⚪ White Division", "🔵 Blue Division"
    ])

    # ── Overview tab ─────────────────────────────────────────────────────────
    with subtab_overview:
        st.subheader(f"Planning {planning_season} — League Overview")
        season_weights = _compute_season_weights(len(all_season_strs))
        weight_str = ", ".join(
            f"{s}: {season_weights[i]*100:.0f}%" for i, s in enumerate(all_season_strs)
        )
        st.caption(f"Analysis based on {len(all_season_strs)} seasons: {', '.join(all_season_strs)}")
        st.caption(f"Season weights: {weight_str}")
        st.caption("Metric weights: Avg Diff per meet 65%, Total Pt Diff 35%")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Teams", len(df_current))
        with col2:
            st.metric("Total Swimmers", df_current['Roster Size'].sum())
        with col3:
            st.metric("Consider Move Up", len(df_current[df_current['Flag'] == '⬆️']))
        with col4:
            st.metric("Consider Move Down", len(df_current[df_current['Flag'] == '⬇️']))

        st.markdown("---")
        st.markdown("**Recommendation Legend:**")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("⬆️ Consider Move Up")
            st.markdown("⬇️ Consider Move Down")
        with col2:
            st.markdown("📈 Improving (blocks move down)")
            st.markdown("📉 Declining (blocks move up)")
        with col3:
            st.markdown("🔄 Recently Moved (adjusting)")
            st.markdown("✓ Well Placed")
        st.caption(
            "*Trend direction can override raw numbers - a declining team won't be "
            "recommended to move up even with strong results.*"
        )

        st.markdown("---")
        st.markdown("### Division Summary")
        for div_name, div_info in _DIVISION_INFO.items():
            df_div = df_current[df_current['Division'] == div_name].copy()
            if len(df_div) == 0:
                continue
            st.markdown(f"#### {div_info['emoji']} {div_info['name']}")
            df_div = df_div.sort_values('Pt Diff', ascending=False)
            df_disp = df_div[['Team', 'Roster Size', 'W', 'L', 'Pt Diff', 'Avg Diff',
                               'CM Points', 'CM Finish', 'Flag', 'Reason']].copy()
            df_disp['Record'] = df_disp['W'].astype(str) + '-' + df_disp['L'].astype(str)
            df_disp['Pt Diff'] = df_disp['Pt Diff'].apply(lambda x: f"+{x}" if x > 0 else str(x))
            df_disp['Avg Diff'] = df_disp['Avg Diff'].apply(
                lambda x: f"+{x:.1f}" if x > 0 else f"{x:.1f}"
            )
            st.dataframe(
                df_disp[['Team', 'Roster Size', 'Record', 'Pt Diff', 'Avg Diff',
                          'CM Points', 'CM Finish', 'Flag', 'Reason']],
                hide_index=True, use_container_width=True
            )

        st.markdown("---")
        st.markdown("### Cross-Division Balance")
        div_comparison = []
        for div in ['red', 'white', 'blue']:
            div_teams = df_current[df_current['Division'] == div]
            if len(div_teams) > 0:
                div_comparison.append({
                    'Division': f"{_DIVISION_INFO[div]['emoji']} {div.capitalize()}",
                    'Teams': len(div_teams),
                    'Avg Roster': round(div_teams['Roster Size'].mean(), 0),
                    'Avg Pt Diff': round(div_teams['Pt Diff'].mean(), 0),
                    'Total Swimmers': div_teams['Roster Size'].sum()
                })
        if div_comparison:
            df_dc = pd.DataFrame(div_comparison)
            df_dc['Avg Pt Diff'] = df_dc['Avg Pt Diff'].apply(
                lambda x: f"+{int(x)}" if x > 0 else str(int(x))
            )
            st.dataframe(df_dc, hide_index=True, use_container_width=True)

        st.markdown("---")
        st.markdown("### Point Differential by Division")
        available_seasons = [s for s in all_season_strs if s in all_season_data]
        chart_season = st.selectbox(
            "Season", options=available_seasons, index=0, key="pt_diff_chart_season"
        )
        st.caption("Teams grouped by division. Green = positive (outscoring opponents), Red = negative.")
        df_chart = all_season_data[chart_season][
            all_season_data[chart_season]['Division'].isin(['red', 'white', 'blue'])
        ].copy()
        df_chart['Division'] = pd.Categorical(
            df_chart['Division'], categories=['red', 'white', 'blue'], ordered=True
        )
        df_chart = df_chart.sort_values(['Division', 'Pt Diff'], ascending=[True, False])
        colors = df_chart['Pt Diff'].apply(lambda x: '#2ecc71' if x > 0 else '#e74c3c')
        div_emoji = {'red': '🔴', 'white': '⚪', 'blue': '🔵'}
        df_chart['Team Display'] = df_chart.apply(
            lambda r: f"{div_emoji.get(r['Division'], '')} {r['Team']}", axis=1
        )
        fig = go.Figure(go.Bar(
            x=df_chart['Pt Diff'],
            y=df_chart['Team Display'],
            orientation='h',
            marker_color=colors,
            text=df_chart['Pt Diff'].apply(lambda x: f"+{x}" if x > 0 else str(x)),
            textposition='outside'
        ))
        fig.update_layout(
            height=max(500, len(df_chart) * 28),
            margin=dict(l=0, r=60, t=10, b=0),
            xaxis_title="Point Differential",
            yaxis_title="",
            yaxis=dict(categoryorder='array',
                       categoryarray=df_chart['Team Display'].tolist()[::-1])
        )
        fig.add_vline(x=0, line_dash="dash", line_color="gray")
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        st.markdown("### Avg Diff Trend by Division")
        st.caption(
            "Average point differential per meet over seasons. "
            "Trends show team trajectory within their division."
        )
        for div_name, div_info in _DIVISION_INFO.items():
            df_div_trend = df_current[df_current['Division'] == div_name].copy()
            if len(df_div_trend) == 0:
                continue
            st.markdown(f"#### {div_info['emoji']} {div_info['name']}")
            avg_trend_data = []
            for _, row in df_div_trend.iterrows():
                for season in all_season_strs:
                    div_col = f"Div {season}"
                    avg_col = f"AvgDiff {season}"
                    if row.get(div_col) != div_name:
                        continue
                    if avg_col in row.index and pd.notna(row[avg_col]):
                        avg_trend_data.append(
                            {'Team': row['Team'], 'Season': season, 'Avg Diff': row[avg_col]}
                        )
            if avg_trend_data:
                fig = px.line(
                    pd.DataFrame(avg_trend_data), x='Season', y='Avg Diff', color='Team',
                    markers=True
                )
                fig.update_layout(
                    height=300,
                    xaxis_title="Season", yaxis_title="Avg Diff/Meet",
                    legend=dict(orientation='h', yanchor='bottom', y=-0.4, xanchor='center', x=0.5),
                    margin=dict(l=0, r=0, t=10, b=0)
                )
                fig.add_hline(y=0, line_dash="dash", line_color="gray")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No trend data available")

        st.markdown("---")
        st.markdown("### Age Group Distribution")
        st.markdown(
            "**Why this matters for alignment:** Teams with more older swimmers (13-14, 15-18) "
            "typically score more points. A team top-heavy with older swimmers may dominate now "
            "but decline as those swimmers age out. Teams heavy in younger age groups are building "
            "for the future."
        )
        df_age = df_current[['Team', 'Division'] + _AGE_GROUPS].copy()
        df_age_melted = df_age.melt(id_vars=['Team', 'Division'], var_name='Age Group', value_name='Swimmers')
        team_order = df_current.sort_values('Roster Size', ascending=False)['Team'].tolist()
        fig = px.bar(
            df_age_melted, x='Team', y='Swimmers', color='Age Group',
            category_orders={'Team': team_order, 'Age Group': _AGE_GROUPS},
            color_discrete_sequence=['#3498db', '#2ecc71', '#f39c12', '#e74c3c', '#9b59b6']
        )
        fig.update_layout(
            height=450,
            margin=dict(l=0, r=0, t=10, b=0),
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='center', x=0.5),
            xaxis_title="", yaxis_title="Swimmers"
        )
        fig.update_xaxes(tickangle=45)
        st.plotly_chart(fig, use_container_width=True)

        df_age_display = df_current[
            ['Team', 'Division', 'Roster Size'] + _AGE_GROUPS
        ].sort_values('Roster Size', ascending=False)
        st.dataframe(df_age_display, hide_index=True, use_container_width=True, height=350)

    # ── Per-division sub-tabs ─────────────────────────────────────────────────
    for subtab, (div_name, div_info) in zip(
        [subtab_red, subtab_white, subtab_blue], _DIVISION_INFO.items()
    ):
        with subtab:
            df_div = df_current[df_current['Division'] == div_name].copy()
            if len(df_div) == 0:
                st.info(f"No teams assigned to {div_info['name']}")
                continue

            st.subheader(f"{div_info['emoji']} {div_info['name']} - Detailed Analysis")
            st.caption(div_info['desc'])

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Teams", len(df_div))
            with col2:
                st.metric("Total Swimmers", df_div['Roster Size'].sum())
            with col3:
                st.metric("Avg Pt Diff", f"{df_div['Pt Diff'].mean():+.0f}")
            with col4:
                st.metric("Flagged Teams", len(df_div[df_div['Flag'].isin(['⬆️', '⬇️'])]))

            st.markdown("### Team Performance History")
            st.markdown("*Point differential each season (only showing seasons in this division).*")
            df_div = df_div.sort_values('Pt Diff', ascending=False)

            hist_cols = ['Team', 'Roster Size', 'CM Points', 'CM Finish']
            for season in all_season_strs:
                hist_cols += [f"PtDiff {season}", f"AvgDiff {season}"]
            hist_cols += ['Flag', 'Reason']
            hist_cols = [c for c in hist_cols if c in df_div.columns]
            df_hist = df_div[hist_cols].copy()

            for season in all_season_strs:
                div_col = f"Div {season}"
                pt_col = f"PtDiff {season}"
                avg_col = f"AvgDiff {season}"
                if div_col in df_div.columns:
                    for idx in df_hist.index:
                        team_div = df_div.loc[idx, div_col] if div_col in df_div.columns else None
                        if pd.isna(team_div) or team_div != div_name:
                            if pt_col in df_hist.columns:
                                df_hist.loc[idx, pt_col] = None
                            if avg_col in df_hist.columns:
                                df_hist.loc[idx, avg_col] = None

            for season in all_season_strs:
                pt_col = f"PtDiff {season}"
                if pt_col in df_hist.columns:
                    df_hist[pt_col] = df_hist[pt_col].apply(
                        lambda x: f"+{int(x)}" if pd.notna(x) and x > 0
                        else (str(int(x)) if pd.notna(x) else '—')
                    )
                avg_col = f"AvgDiff {season}"
                if avg_col in df_hist.columns:
                    df_hist[avg_col] = df_hist[avg_col].apply(
                        lambda x: f"+{x:.1f}" if pd.notna(x) and x > 0
                        else (f"{x:.1f}" if pd.notna(x) else '—')
                    )
            st.dataframe(df_hist, hide_index=True, use_container_width=True)

            st.markdown("### Division Movement History")
            div_hist_cols = ['Team'] + [f"Div {s}" for s in all_season_strs]
            div_hist_cols = [c for c in div_hist_cols if c in df_div.columns]
            df_div_hist = df_div[div_hist_cols].copy()

            def _highlight_change(row):
                divs = [row.get(f"Div {s}", '—') for s in all_season_strs if f"Div {s}" in row.index]
                divs = [d for d in divs if pd.notna(d) and d != '—']
                return '🔄 Changed' if len(set(divs)) > 1 else ''

            df_div_hist['Movement'] = df_div_hist.apply(_highlight_change, axis=1)
            st.dataframe(df_div_hist, hide_index=True, use_container_width=True)

            st.markdown("### Performance Trends")
            st.caption("Only showing seasons when team was in this division.")

            pt_chart_data = []
            avg_chart_data = []
            for _, row in df_div.iterrows():
                for season in all_season_strs:
                    div_col = f"Div {season}"
                    if row.get(div_col) != div_name:
                        continue
                    pt_col = f"PtDiff {season}"
                    avg_col = f"AvgDiff {season}"
                    if pt_col in row.index and pd.notna(row[pt_col]):
                        val = row[pt_col]
                        if isinstance(val, str):
                            val = int(val.replace('+', ''))
                        pt_chart_data.append({'Team': row['Team'], 'Season': season, 'Pt Diff': val})
                    if avg_col in row.index and pd.notna(row[avg_col]):
                        val = row[avg_col]
                        if isinstance(val, str):
                            val = float(val.replace('+', ''))
                        avg_chart_data.append({'Team': row['Team'], 'Season': season, 'Avg Diff': val})

            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Total Point Differential**")
                if pt_chart_data:
                    fig = px.line(pd.DataFrame(pt_chart_data), x='Season', y='Pt Diff',
                                  color='Team', markers=True)
                    fig.update_layout(
                        height=350, xaxis_title="Season", yaxis_title="Total Pt Diff",
                        legend=dict(orientation='h', yanchor='bottom', y=-0.3,
                                    xanchor='center', x=0.5)
                    )
                    fig.add_hline(y=0, line_dash="dash", line_color="gray")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No data available")

            with col2:
                st.markdown("**Avg Diff per Meet**")
                if avg_chart_data:
                    fig = px.line(pd.DataFrame(avg_chart_data), x='Season', y='Avg Diff',
                                  color='Team', markers=True)
                    fig.update_layout(
                        height=350, xaxis_title="Season", yaxis_title="Avg Diff/Meet",
                        legend=dict(orientation='h', yanchor='bottom', y=-0.3,
                                    xanchor='center', x=0.5)
                    )
                    fig.add_hline(y=0, line_dash="dash", line_color="gray")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No data available")

    # ── Download ──────────────────────────────────────────────────────────────
    st.markdown("---")
    export_cols = ['Team', 'Code', 'Division', 'Roster Size', 'W', 'L',
                   'Pt Diff', 'CM Points', 'Flag', 'Reason']
    for season in all_season_strs:
        export_cols += [f"PtDiff {season}", f"Div {season}"]
    df_export = df_current[[c for c in export_cols if c in df_current.columns]].copy()
    st.download_button(
        label="Download Complete Alignment Data (CSV)",
        data=df_export.to_csv(index=False),
        file_name=f"alignment_analysis_planning_{planning_season}.csv",
        mime="text/csv"
    )
