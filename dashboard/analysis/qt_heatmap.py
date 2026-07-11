"""
Qualification Rate Heatmap

Shows qual rates for all events at a glance, colored by delta from a user-specified target rate.
Blue = below target (standard too strict), Red = above target (too lenient), White = on target.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

AGE_GROUP_ORDER = ['6 & Under', '7-8', '9-10', '11-12', '13-14', '15-18']

# Young age groups receive a 5% higher qualification target to foster growth
YOUNG_AGE_GROUPS = {'6 & Under', '7-8', '8 & Under'}
YOUNG_BONUS = 5.0


def render_qt_heatmap(agg_stats_df: pd.DataFrame, target_rate: float) -> None:
    """Render the qualification rate heatmap in Streamlit.

    Args:
        agg_stats_df: Full (unfiltered) stats DataFrame from compute_event_statistics().
        target_rate: Target qualification rate as a percentage (e.g. 33).
    """
    if agg_stats_df is None or agg_stats_df.empty:
        st.info("No data available for heatmap.")
        return

    gender_label = st.radio(
        "Gender", ["Girls", "Boys"], horizontal=True, key="heatmap_gender"
    )
    gender_code = "F" if gender_label == "Girls" else "M"

    df = agg_stats_df[agg_stats_df["gender"] == gender_code].copy()
    if df.empty:
        st.info(f"No data for {gender_label}.")
        return

    df["event_label"] = df["distance"].astype(str) + "m " + df["stroke"]

    # Pivot: rows = age_group (ordered), columns = event_label, values = qual_rate
    pivot = df.pivot_table(
        index="age_group", columns="event_label", values="qual_rate", aggfunc="first"
    )

    # Reorder rows to canonical age group order
    ordered_rows = [ag for ag in AGE_GROUP_ORDER if ag in pivot.index]
    pivot = pivot.reindex(ordered_rows)

    # Sort columns by distance then stroke for a logical left-to-right order
    col_order = (
        df[["event_label", "distance", "stroke"]]
        .drop_duplicates()
        .sort_values(["distance", "stroke"])["event_label"]
        .tolist()
    )
    col_order = [c for c in col_order if c in pivot.columns]
    pivot = pivot[col_order]

    # Per-age-group target matrix: young groups get target + 5%
    effective_target = pd.Series(
        {ag: target_rate + YOUNG_BONUS if ag in YOUNG_AGE_GROUPS else target_rate
         for ag in pivot.index},
        name="target"
    )
    target_matrix = pd.DataFrame(
        {col: effective_target for col in pivot.columns}, index=pivot.index
    )

    # Delta matrix (positive = above target = lenient, negative = below = strict)
    delta = pivot - target_matrix

    # Annotation text: actual qual_rate as "XX%" for non-NaN cells
    text_matrix = pivot.map(lambda v: f"{v:.0f}%" if pd.notna(v) else "")

    # RdBu_r: negative delta (too strict) → red, positive (too lenient) → blue, 0 → white
    # yaxis/xaxis type='category' prevents Plotly from misinterpreting age-group
    # strings like "7-8" or "9-10" as dates, which causes all cells to go blank.
    fig = go.Figure(go.Heatmap(
        z=delta.values,
        x=delta.columns.tolist(),
        y=delta.index.tolist(),
        colorscale="RdBu_r",
        zmid=0,
        text=text_matrix.values,
        texttemplate="%{text}",
        textfont={"size": 11},
        hoverongaps=False,
        colorbar={"title": "Δ from target"},
    ))
    fig.update_layout(
        title=f"{gender_label} — Qualification Rate vs {target_rate:.0f}% Target",
        height=350,
        yaxis={"type": "category", "title": None},
        xaxis={"type": "category", "title": None},
    )

    st.plotly_chart(fig, use_container_width=True, theme=None)
    st.caption(
        f"Color shows how far each event's actual qual rate is from its target. "
        f"6&U / 7-8 / 8&U use **{target_rate + YOUNG_BONUS:.0f}%** target; all other age groups use **{target_rate:.0f}%**. "
        "**Blue** = too few qualifiers (standard is too strict). "
        "**Red** = too many qualifiers (standard is too lenient). "
        "**White** = on target."
    )
