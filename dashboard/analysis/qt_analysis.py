"""
Qualifying Time Analysis

Renders the QT Analysis tab: heatmap, event summary table, sensitivity analysis,
and detailed per-event charts for setting City Meet qualifying time standards.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from dashboard.analysis.qt_heatmap import render_qt_heatmap
from dashboard.analysis.qt_sensitivity import render_qt_sensitivity
from dashboard.analysis.qualifying_times import (
    get_standards_df,
    format_era,
    get_all_personal_bests,
    compute_event_statistics,
    compute_yearly_statistics,
    get_city_meet_participation,
    get_cm_stats_by_standard,
    load_comparison_standards,
    format_time,
    round_to_standard,
    get_times_for_event,
)


def render_qt_analysis(session) -> None:
    """Render the Qualifying Time Analysis tab."""
    st.header("Qualifying Time Analysis")
    st.markdown("""
    **What is this?** This tool helps you set fair qualifying times (QTs) for City Meet.
    It looks at how fast swimmers actually swim during the season and shows what percentage
    of the league would qualify at any given cutoff.

    **How it works:**
    - We look at each swimmer's **best time** during the season (from dual meets, invitationals, and exhibitions)
    - Times are grouped by the **swimmer's age** (not the event age group they swam in)
    - The **P35 recommendation** is the time that the 35th-fastest swimmer achieved — if you set the QT there, about 35% of swimmers would qualify

    **Goal:** Set qualifying times that reflect a consistent, data-driven percentage of eligible swimmers.

    **Young age group policy:** 6 & Under, 7-8, and 8 & Under events use a qualification target
    5 percentage points higher than the base target (e.g. 40% instead of 35%) to foster growth
    and encourage participation in the sport at younger ages.
    """)

    # Load data
    @st.cache_data(ttl=3600)
    def _load_qt_data(_session_id):
        standards = get_standards_df(session)
        personal_bests = get_all_personal_bests(session)
        if personal_bests.empty or standards.empty:
            return None, None, None, None, None
        agg_stats = compute_event_statistics(personal_bests, standards)
        yearly_stats = compute_yearly_statistics(personal_bests, standards)

        cm_participation = get_city_meet_participation(session)
        cm_stats = get_cm_stats_by_standard(cm_participation, standards) if not cm_participation.empty else pd.DataFrame()

        return standards, personal_bests, agg_stats, yearly_stats, cm_stats

    with st.spinner("Loading swim data..."):
        standards_df, personal_bests_df, agg_stats_df, yearly_stats_df, cm_stats_df = _load_qt_data(id(session))

    if standards_df is None or agg_stats_df is None or agg_stats_df.empty:
        st.warning("No data available. Ensure City Meet standards are loaded and swim data has been imported.")
        return

    # Standards are season-scoped; this tab compares the current (active) set
    # against the full history of swims to inform the next adoption.
    if 'season_start' in standards_df.columns and not standards_df.empty:
        active_era = format_era(
            standards_df['season_start'].iloc[0], standards_df['season_end'].iloc[0]
        )
        st.caption(f"Comparing against the current **{active_era}** qualifying standards.")

    # Merge City Meet stats into aggregate stats (average CM swimmers across years)
    if cm_stats_df is not None and not cm_stats_df.empty:
        cm_agg = cm_stats_df.groupby(['gender', 'age_group', 'distance', 'stroke', 'event_name']).agg(
            cm_swimmers_avg=('cm_swimmers', 'mean'),
            cm_swimmers_last=('cm_swimmers', 'last'),
            cm_years=('season', 'nunique'),
        ).reset_index()
        agg_stats_df = agg_stats_df.merge(
            cm_agg[['event_name', 'cm_swimmers_avg', 'cm_swimmers_last', 'cm_years']],
            on='event_name', how='left'
        )
        agg_stats_df['cm_swimmers_avg'] = agg_stats_df['cm_swimmers_avg'].fillna(0)
        agg_stats_df['cm_swimmers_last'] = agg_stats_df['cm_swimmers_last'].fillna(0)
    else:
        agg_stats_df['cm_swimmers_avg'] = 0
        agg_stats_df['cm_swimmers_last'] = 0
        agg_stats_df['cm_years'] = 0

    # Load VPSU comparison standards
    vpsu_standards = load_comparison_standards()
    if not vpsu_standards.empty:
        vpsu_standards['merge_key'] = (
            vpsu_standards['gender'] + '_' +
            vpsu_standards['distance'].astype(str) + '_' +
            vpsu_standards['stroke']
        )
        agg_stats_df['merge_key'] = (
            agg_stats_df['gender'] + '_' +
            agg_stats_df['distance'].astype(str) + '_' +
            agg_stats_df['stroke']
        )

        vpsu_lookup = vpsu_standards.set_index(['gender', 'distance', 'stroke', 'age_group'])[
            ['standard_seconds', 'standard_formatted']
        ].to_dict('index')

        def get_vpsu_standard(row):
            key = (row['gender'], row['distance'], row['stroke'], row['age_group'])
            if key in vpsu_lookup:
                return vpsu_lookup[key]['standard_seconds'], vpsu_lookup[key]['standard_formatted']
            return None, None

        agg_stats_df['vpsu_seconds'], agg_stats_df['vpsu_formatted'] = zip(
            *agg_stats_df.apply(get_vpsu_standard, axis=1)
        )
        agg_stats_df.drop(columns=['merge_key'], inplace=True)

        standards_lookup = standards_df.set_index(['gender', 'distance', 'stroke', 'age_group'])

        def calc_vpsu_qual_rate(row):
            if pd.isna(row['vpsu_seconds']):
                return None
            try:
                std_row = standards_lookup.loc[(row['gender'], row['distance'], row['stroke'], row['age_group'])]
                age_lower = std_row['age_group_lower']
                age_upper = std_row['age_group_upper']
            except KeyError:
                return None

            mask = (
                (personal_bests_df['gender'] == row['gender']) &
                (personal_bests_df['distance'] == row['distance']) &
                (personal_bests_df['stroke'] == row['stroke']) &
                (personal_bests_df['age_group_lower'] >= age_lower) &
                (personal_bests_df['age_group_upper'] <= age_upper)
            )
            times = personal_bests_df.loc[mask, 'best_time']
            if len(times) == 0:
                return None
            return (times <= row['vpsu_seconds']).mean() * 100

        agg_stats_df['vpsu_qual_rate'] = agg_stats_df.apply(calc_vpsu_qual_rate, axis=1)
    else:
        agg_stats_df['vpsu_seconds'] = None
        agg_stats_df['vpsu_formatted'] = None
        agg_stats_df['vpsu_qual_rate'] = None

    # Target rate input (shared by heatmap and sensitivity table)
    target_rate = st.number_input(
        "Target qualification rate (%)",
        min_value=10, max_value=60, value=33, step=1,
        help="The % of eligible swimmers you want to qualify for City Meet.",
        key="qt_target_rate",
    )

    st.markdown("---")
    st.subheader("Qualification Rate Heatmap")
    render_qt_heatmap(agg_stats_df, target_rate)

    st.markdown("---")

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        gender_filter = st.selectbox("Gender", ['All', 'Girls', 'Boys'], key="qt_gender")
    with col2:
        age_group_options = ['All'] + sorted(agg_stats_df['age_group'].unique().tolist())
        age_group_filter = st.selectbox("Age Group", age_group_options, key="qt_age_group")
    with col3:
        stroke_options = ['All'] + sorted(agg_stats_df['stroke'].unique().tolist())
        stroke_filter = st.selectbox("Stroke", stroke_options, key="qt_stroke")

    # Apply filters
    filtered_stats = agg_stats_df.copy()
    filtered_yearly = yearly_stats_df.copy()
    filtered_pb = personal_bests_df.copy()

    if gender_filter != 'All':
        gender_code = 'F' if gender_filter == 'Girls' else 'M'
        filtered_stats = filtered_stats[filtered_stats['gender'] == gender_code]
        filtered_yearly = filtered_yearly[filtered_yearly['gender'] == gender_code]
        filtered_pb = filtered_pb[filtered_pb['gender'] == gender_code]
    if age_group_filter != 'All':
        filtered_stats = filtered_stats[filtered_stats['age_group'] == age_group_filter]
        filtered_yearly = filtered_yearly[filtered_yearly['age_group'] == age_group_filter]
    if stroke_filter != 'All':
        filtered_stats = filtered_stats[filtered_stats['stroke'] == stroke_filter]
        filtered_yearly = filtered_yearly[filtered_yearly['stroke'] == stroke_filter]

    if filtered_stats.empty:
        st.info("No events match the selected filters.")
        return

    # Summary table
    st.subheader("Event Summary")
    st.markdown("""
    **Quick guide to this table:**
    - **GPSA / VPSU** = Qualifying time standards for each league
    - **GPSA % / VPSU %** = Percentage of swimmers who would qualify under each league's standards
    - **CM Avg** = Average swimmers at City Meet
    - **P35 (Rec)** = Recommended QT based on 35th percentile (rounded to nearest 0.25s)
    - **Delta** = Difference between P35 recommendation and current GPSA QT
      - *Negative* = GPSA QT is slower (more inclusive) than P35
      - *Positive* = GPSA QT is faster (more exclusive) than P35
    """)

    summary_display = filtered_stats[[
        'event_name', 'current_qt_formatted', 'vpsu_formatted', 'qual_rate', 'vpsu_qual_rate',
        'cm_swimmers_avg', 'p35', 'current_qt'
    ]].copy()

    summary_display['p35_rounded'] = summary_display['p35'].apply(round_to_standard)
    summary_display['delta'] = summary_display['p35_rounded'] - summary_display['current_qt']

    def get_flag_and_reason(row):
        delta = row['delta']
        if delta < -2.0:
            return ('⬇️', 'Standard too lenient')
        elif delta < -0.5:
            return ('⬇️', 'Consider faster QT')
        elif abs(delta) <= 0.5:
            return ('✅', 'On target')
        elif delta <= 2.0:
            return ('⬆️', 'Consider slower QT')
        else:
            return ('⬆️', 'Standard too strict')

    summary_display['Flag'], summary_display['Reason'] = zip(
        *summary_display.apply(get_flag_and_reason, axis=1)
    )

    summary_display = summary_display[[
        'event_name', 'current_qt_formatted', 'qual_rate', 'vpsu_formatted', 'vpsu_qual_rate',
        'cm_swimmers_avg', 'p35_rounded', 'delta', 'Flag', 'Reason'
    ]]
    summary_display.columns = [
        'Event', 'GPSA', 'GPSA %', 'VPSU', 'VPSU %',
        'CM Avg', 'P35 (Rec)', 'Delta (s)', 'Flag', 'Recommendation'
    ]

    summary_display['P35 (Rec)'] = summary_display['P35 (Rec)'].apply(format_time)
    summary_display['CM Avg'] = summary_display['CM Avg'].apply(lambda x: f"{x:.0f}" if x > 0 else "-")
    summary_display['VPSU'] = summary_display['VPSU'].fillna("-")
    summary_display['VPSU %'] = summary_display['VPSU %'].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "-")

    st.dataframe(
        summary_display,
        column_config={
            "GPSA %": st.column_config.ProgressColumn(
                "GPSA %", help="% who qualify under GPSA standards", format="%.1f%%", min_value=0, max_value=100
            ),
            "VPSU %": st.column_config.TextColumn("VPSU %", help="% who would qualify under VPSU standards"),
            "CM Avg": st.column_config.TextColumn("CM Avg", help="Average swimmers at City Meet"),
            "Delta (s)": st.column_config.NumberColumn("Delta (s)", format="%.2f"),
        },
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("""
    **Flags:**
    ✅ On target |
    ⬆️ Consider slower QT |
    ⬇️ Could make faster |
    ⚠️ Monitor |
    🚫 Don't make faster |
    ❓ No CM data
    """)

    csv = summary_display.to_csv(index=False)
    st.download_button("Download Summary CSV", csv, "qt_summary.csv", "text/csv")

    st.markdown("---")
    st.subheader("Sensitivity Analysis")
    render_qt_sensitivity(filtered_stats, target_rate)

    st.markdown("---")

    # Detailed event analysis
    st.subheader("Detailed Event Analysis")
    st.markdown("*Select an event below to see detailed charts and year-by-year breakdown.*")
    event_names = filtered_stats['event_name'].tolist()
    selected_event = st.selectbox("Select Event", event_names, key="qt_event_select")

    if selected_event:
        event_row = filtered_stats[filtered_stats['event_name'] == selected_event].iloc[0]

        std_row = standards_df[
            (standards_df['gender'] == event_row['gender']) &
            (standards_df['distance'] == event_row['distance']) &
            (standards_df['stroke'] == event_row['stroke']) &
            (standards_df['age_group'] == event_row['age_group'])
        ].iloc[0]

        event_times = get_times_for_event(
            filtered_pb,
            std_row['gender'],
            std_row['age_group_lower'],
            std_row['age_group_upper'],
            std_row['distance'],
            std_row['stroke'],
        )

        event_cm = cm_stats_df[cm_stats_df['event_name'] == selected_event] if cm_stats_df is not None and not cm_stats_df.empty else pd.DataFrame()
        cm_avg = event_row.get('cm_swimmers_avg', 0)

        p35_rounded = round_to_standard(event_row['p35'])
        delta_rounded = p35_rounded - event_row['current_qt']

        if delta_rounded < -2.0:
            st.error("⬇️ **Standard too lenient** — current QT is {:.2f}s slower than P35.".format(abs(delta_rounded)))
        elif delta_rounded < -0.5:
            st.warning("⬇️ **Consider a faster time** — current QT is {:.2f}s slower than P35.".format(abs(delta_rounded)))
        elif abs(delta_rounded) <= 0.5:
            st.success("✅ **On target** — current QT is within 0.5s of P35.")
        elif delta_rounded <= 2.0:
            st.warning("⬆️ **Consider a slower time** — current QT is {:.2f}s faster than P35.".format(delta_rounded))
        else:
            st.error("⬆️ **Standard too strict** — current QT is {:.2f}s faster than P35.".format(delta_rounded))

        vpsu_qt = event_row.get('vpsu_seconds')
        vpsu_formatted = event_row.get('vpsu_formatted', '-')
        vpsu_qual_rate = event_row.get('vpsu_qual_rate')

        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1:
            st.metric("GPSA QT", event_row['current_qt_formatted'])
        with col2:
            st.metric("GPSA Qual %", f"{event_row['qual_rate']:.1f}%")
        with col3:
            if vpsu_qt and not pd.isna(vpsu_qt):
                vpsu_delta = vpsu_qt - event_row['current_qt']
                st.metric("VPSU QT", vpsu_formatted,
                         delta=f"{vpsu_delta:+.2f}s" if vpsu_delta != 0 else "same")
            else:
                st.metric("VPSU QT", "-")
        with col4:
            if vpsu_qual_rate and not pd.isna(vpsu_qual_rate):
                qual_diff = vpsu_qual_rate - event_row['qual_rate']
                st.metric("VPSU Qual %", f"{vpsu_qual_rate:.1f}%",
                         delta=f"{qual_diff:+.1f}%" if qual_diff != 0 else "same")
            else:
                st.metric("VPSU Qual %", "-")
        with col5:
            st.metric("P35 (Rec)", format_time(p35_rounded),
                     delta=f"{delta_rounded:+.2f}s" if not pd.isna(delta_rounded) else None)
        with col6:
            st.metric("CM Avg", f"{cm_avg:.0f}" if cm_avg > 0 else "N/A")

        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            st.markdown("**Time Distribution (All Years)**")
            st.caption("Each bar shows how many swimmers had their best time in that range. "
                      "Red = GPSA QT, Purple = VPSU QT, Green = P35 recommendation.")
            fig_hist = px.histogram(
                event_times, x='best_time',
                labels={'best_time': 'Time (seconds)', 'count': 'Swimmers'}
            )
            fig_hist.update_traces(xbins_size=1)
            fig_hist.add_vline(x=event_row['current_qt'], line_dash="dash", line_color="red",
                               annotation_text="GPSA", annotation_position="top right")
            vpsu_qt = event_row.get('vpsu_seconds')
            if vpsu_qt and not pd.isna(vpsu_qt):
                fig_hist.add_vline(x=vpsu_qt, line_dash="dash", line_color="purple",
                                   annotation_text="VPSU", annotation_position="top right")
            fig_hist.add_vline(x=p35_rounded, line_dash="dash", line_color="green",
                               annotation_text="P35", annotation_position="top left")
            fig_hist.update_layout(showlegend=False, margin=dict(t=20))
            st.plotly_chart(fig_hist, use_container_width=True)

        with chart_col2:
            st.markdown("**Year-over-Year Trends**")
            st.caption("Are swimmers getting faster or slower over time? "
                      "If the lines are dropping, swimmers are getting faster. "
                      "The red dashed line is the current QT for reference.")
            event_yearly = filtered_yearly[filtered_yearly['event_name'] == selected_event].sort_values('season')

            if not event_yearly.empty:
                fig_trend = go.Figure()
                fig_trend.add_trace(go.Scatter(
                    x=event_yearly['season'], y=event_yearly['p35'].apply(round_to_standard),
                    mode='lines+markers', name='P35 (rounded)',
                    line=dict(color='green')
                ))
                fig_trend.add_trace(go.Scatter(
                    x=event_yearly['season'], y=event_yearly['median'],
                    mode='lines+markers', name='Median',
                    line=dict(color='blue')
                ))
                fig_trend.add_trace(go.Scatter(
                    x=event_yearly['season'], y=event_yearly['mean'],
                    mode='lines+markers', name='Mean',
                    line=dict(color='orange')
                ))
                fig_trend.add_hline(y=event_row['current_qt'], line_dash="dash", line_color="red",
                                    annotation_text="Current QT")
                fig_trend.update_layout(
                    xaxis_title="Season",
                    yaxis_title="Time (seconds)",
                    xaxis=dict(tickmode='linear'),
                    margin=dict(t=20),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02)
                )
                st.plotly_chart(fig_trend, use_container_width=True)
            else:
                st.info("No yearly data available for this event.")

        st.markdown("**Yearly Breakdown**")
        st.caption("Compare each season side-by-side. CM Swimmers = actual City Meet participants. "
                  "Eligible = swimmers with a recorded time who could potentially qualify.")
        if not event_yearly.empty:
            yearly_display = event_yearly[[
                'season', 'n_swimmers', 'qualifiers', 'qual_rate', 'p35'
            ]].copy()

            if not event_cm.empty:
                cm_by_year = event_cm[['season', 'cm_swimmers']].copy()
                yearly_display = yearly_display.merge(cm_by_year, on='season', how='left')
                yearly_display['cm_swimmers'] = yearly_display['cm_swimmers'].fillna(0).astype(int)
            else:
                yearly_display['cm_swimmers'] = 0

            yearly_display['p35'] = yearly_display['p35'].apply(round_to_standard)
            yearly_display = yearly_display[['season', 'cm_swimmers', 'n_swimmers', 'qualifiers', 'qual_rate', 'p35']]
            yearly_display.columns = ['Season', 'CM Swimmers', 'Eligible', 'Qualifiers', 'Qual %', 'P35']
            yearly_display['P35'] = yearly_display['P35'].apply(format_time)
            yearly_display['Qual %'] = yearly_display['Qual %'].apply(lambda x: f"{x:.1f}%")
            st.dataframe(yearly_display, use_container_width=True, hide_index=True)

        if not event_cm.empty:
            cm_col1, cm_col2 = st.columns(2)

            with cm_col1:
                st.markdown("**City Meet Participation by Year**")
                st.caption("How many swimmers actually swam this event at City Meet each year.")
                fig_cm = px.bar(
                    event_cm.sort_values('season'), x='season', y='cm_swimmers',
                    labels={'season': 'Season', 'cm_swimmers': 'Swimmers'},
                    text='cm_swimmers'
                )
                fig_cm.update_layout(margin=dict(t=20), xaxis=dict(tickmode='linear'))
                fig_cm.update_traces(textposition='outside')
                st.plotly_chart(fig_cm, use_container_width=True)

            with cm_col2:
                st.markdown("**Time Distribution by Year (Box Plot)**")
                st.caption("Each box shows where most swimmers' times fall. "
                          "The line in the middle is the median (50th percentile). "
                          "Dots are outliers (unusually fast or slow).")
                fig_box = px.box(
                    event_times, x='season', y='best_time',
                    labels={'season': 'Season', 'best_time': 'Time (seconds)'}
                )
                fig_box.add_hline(y=event_row['current_qt'], line_dash="dash", line_color="red",
                                  annotation_text="Current QT")
                fig_box.add_hline(y=p35_rounded, line_dash="dash", line_color="green",
                                  annotation_text="P35")
                fig_box.update_layout(margin=dict(t=20))
                st.plotly_chart(fig_box, use_container_width=True)
        else:
            st.markdown("**Time Distribution by Year (Box Plot)**")
            st.caption("Each box shows where most swimmers' times fall. "
                      "The line in the middle is the median. Dots are outliers.")
            fig_box = px.box(
                event_times, x='season', y='best_time',
                labels={'season': 'Season', 'best_time': 'Time (seconds)'}
            )
            fig_box.add_hline(y=event_row['current_qt'], line_dash="dash", line_color="red",
                              annotation_text="Current QT")
            fig_box.update_layout(margin=dict(t=20))
            st.plotly_chart(fig_box, use_container_width=True)
