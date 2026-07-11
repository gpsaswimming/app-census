"""
Sensitivity Analysis Table

Shows what qualification rate you'd get at different percentile thresholds,
helping you decide which target percentile to use when setting qualifying times.
"""
import pandas as pd
import streamlit as st

from dashboard.analysis.qualifying_times import format_time

# Percentile columns in ascending order (target rate increases with percentile)
PERCENTILE_COLS = [
    ("p25", 25),
    ("p30", 30),
    ("p35", 35),
    ("p40", 40),
    ("p45", 45),
    ("p50", 50),
]

# Young age groups receive a 5% higher qualifying target
YOUNG_AGE_GROUPS = {'6 & Under', '7-8', '8 & Under'}
YOUNG_BONUS = 5.0


def _closest_percentile(target_rate: float) -> int:
    """Return the percentile value (e.g. 35) closest to target_rate."""
    return min(PERCENTILE_COLS, key=lambda pc: abs(pc[1] - target_rate))[1]


def render_qt_sensitivity(filtered_stats: pd.DataFrame, target_rate: float) -> None:
    """Render the sensitivity analysis table in Streamlit.

    Args:
        filtered_stats: Per-event stats DataFrame (may be gender/age/stroke-filtered).
        target_rate: Target qualification rate as a percentage (e.g. 33).
    """
    if filtered_stats is None or filtered_stats.empty:
        st.info("No events to display in sensitivity analysis.")
        return

    star_pct_base = _closest_percentile(target_rate)
    star_pct_young = _closest_percentile(target_rate + YOUNG_BONUS)

    # Build display rows
    rows = []
    for _, row in filtered_stats.iterrows():
        is_young = row.get("age_group", "") in YOUNG_AGE_GROUPS
        star_pct = star_pct_young if is_young else star_pct_base

        display_row = {
            "Event": row["event_name"],
            "Current QT": row["current_qt_formatted"],
        }

        # Qual rate column (raw float for ProgressColumn)
        display_row["Qual Rate (%)"] = row["qual_rate"]

        for col_key, pct in PERCENTILE_COLS:
            label = f"P{pct} (~{pct}%)"
            if pct == star_pct:
                label = f"★ P{pct} (~{pct}%)"
            val = row.get(col_key)
            display_row[label] = format_time(val) if pd.notna(val) else "N/A"

        rows.append(display_row)

    display_df = pd.DataFrame(rows)

    # Build column_config: ProgressColumn for qual rate, TextColumn for the rest
    col_config = {
        "Qual Rate (%)": st.column_config.ProgressColumn(
            "Current Qual %",
            help="% of eligible swimmers who qualify at the current QT",
            format="%.1f%%",
            min_value=0,
            max_value=100,
        ),
    }
    for col_key, pct in PERCENTILE_COLS:
        label = f"P{pct} (~{pct}%)"
        if pct == star_pct:
            label = f"★ P{pct} (~{pct}%)"
        col_config[label] = st.column_config.TextColumn(
            label,
            help=f"Time at which ~{pct}% of swimmers would qualify",
        )

    st.dataframe(
        display_df,
        column_config=col_config,
        use_container_width=True,
        hide_index=True,
    )

    csv = display_df.to_csv(index=False)
    st.download_button(
        "Download Sensitivity CSV",
        csv,
        "qt_sensitivity.csv",
        "text/csv",
        key="qt_sensitivity_csv",
    )

    st.caption(
        "Set QT to the column nearest your target rate. "
        "**★** marks the closest percentile to your target. "
        f"6&U / 7-8 / 8&U rows are starred at **target + 5%** to support growth in younger age groups."
    )
