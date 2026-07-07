"""Qualifying Time (QT) Analysis Module.

Analyzes historical swim data to help set appropriate City Meet qualifying
standards. Each standard is judged against the SWIMMER'S OWN age group (the
band stored on the athlete), not the event bracket they swam in.

DOB-free note: the old census keyed this on each swim's exact ``league_age``.
The rebuilt schema stores no exact age — only the athlete's age-group band and
its integer bounds (``age_group_lower``/``age_group_upper``). A swimmer counts
toward a standard when their whole band falls inside the standard's age range
(band containment), which reproduces the old per-age matching at group
granularity (GPSA standards are defined on the same bands).
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from db.models import Athlete, CityMeetStandard, Event, Meet, Result

# Path to comparison (VPSU) standards, at the repo-root data/ dir.
COMPARISON_STANDARDS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "vpsu_standards_2025.csv",
)

# QT recommendation policy constants
YOUNG_AGE_GROUPS = {"6 & Under", "7-8", "8 & Under"}
YOUNG_BONUS_PCT = 5.0   # Young groups target this many percentage points higher
MIN_CHANGE_SECONDS = 0.5  # Changes smaller than this are left unchanged


def apply_min_change_threshold(proposed: float, current: float) -> float:
    """Return proposed time only if it differs from current by >= MIN_CHANGE_SECONDS."""
    if abs(proposed - current) < MIN_CHANGE_SECONDS:
        return current
    return proposed


def load_comparison_standards(filepath: str = None) -> pd.DataFrame:
    """Load comparison league (VPSU) standards from CSV, or empty on failure."""
    if filepath is None:
        filepath = COMPARISON_STANDARDS_PATH
    if not os.path.exists(filepath):
        return pd.DataFrame()
    try:
        return pd.read_csv(filepath)
    except Exception:
        return pd.DataFrame()


def get_standard_eras(session: Session) -> list[tuple[int, int]]:
    """Return the distinct ``(season_start, season_end)`` standard ranges, ascending."""
    rows = (
        session.query(CityMeetStandard.season_start, CityMeetStandard.season_end)
        .distinct()
        .order_by(CityMeetStandard.season_start)
        .all()
    )
    return [(r.season_start, r.season_end) for r in rows]


def format_era(season_start: int, season_end: int) -> str:
    """Human-readable label for an effective-season range (e.g. '2026-2027')."""
    if season_start is None or season_end is None:
        return "all seasons"
    return str(season_start) if season_start == season_end else f"{season_start}-{season_end}"


def get_active_season(session: Session) -> int | None:
    """Return the last season covered by any standard set (the newest era's end)."""
    return session.query(func.max(CityMeetStandard.season_end)).scalar()


def get_standards_df(session: Session, season: int = None) -> pd.DataFrame:
    """Load City Meet standards into a DataFrame with a computed age_group label.

    Standards are season-scoped. Pass ``season`` to load the set whose
    effective-season range covers it; when omitted, the most recent (active) set
    is returned, so callers never silently pool multiple eras.
    """
    query = session.query(CityMeetStandard)
    if season is not None:
        query = query.filter(
            CityMeetStandard.season_start <= season,
            CityMeetStandard.season_end >= season,
        )
    else:
        latest = get_active_season(session)
        if latest is not None:
            query = query.filter(CityMeetStandard.season_end == latest)
    standards = query.all()
    if not standards:
        return pd.DataFrame()

    data = []
    for s in standards:
        if s.age_group_upper <= 6:
            age_group = "6 & Under"
        elif s.age_group_upper <= 8:
            age_group = "8 & Under" if s.age_group_lower == 0 else "7-8"
        elif s.age_group_upper <= 10:
            age_group = "10 & Under" if s.age_group_lower == 0 else "9-10"
        elif s.age_group_upper <= 12:
            age_group = "11-12"
        elif s.age_group_upper <= 14:
            age_group = "13-14"
        else:
            age_group = "15-18"

        data.append({
            "gender": s.gender,
            "age_group": age_group,
            "age_group_lower": s.age_group_lower,
            "age_group_upper": s.age_group_upper,
            "distance": s.distance,
            "stroke": s.stroke,
            "standard_seconds": s.standard_seconds,
            "standard_formatted": s.standard_formatted,
            "season_start": s.season_start,
            "season_end": s.season_end,
        })

    return pd.DataFrame(data)


def _in_band(df: pd.DataFrame, std) -> pd.Series:
    """Boolean mask: rows whose own age band is contained by the standard's range.

    Replaces the old ``league_age BETWEEN lower AND upper`` per-age test. A
    swimmer's band ``[lower, upper]`` matches a standard band ``[sl, su]`` when
    ``sl <= lower`` and ``upper <= su`` — i.e. the swimmer's whole age group sits
    inside the standard's range (honoring combined brackets like "8 & Under").
    """
    return (
        (df["gender"] == std["gender"])
        & (df["age_group_lower"] >= std["age_group_lower"])
        & (df["age_group_upper"] <= std["age_group_upper"])
        & (df["distance"] == std["distance"])
        & (df["stroke"] == std["stroke"])
    )


def get_all_personal_bests(session: Session, seasons: list[int] = None) -> pd.DataFrame:
    """Get each swimmer's best time per event type per season.

    Grouped by the season-scoped athlete (which already encodes gender, own age
    group, and team) + distance + stroke + season, giving the best time for
    analysis regardless of which specific event bracket they swam.
    """
    query = (
        session.query(
            Athlete.id.label("swimmer_id"),
            Athlete.full_name,
            Athlete.gender,
            Athlete.age_group,
            Athlete.age_group_lower,
            Athlete.age_group_upper,
            Event.distance,
            Event.stroke,
            Meet.season,
            func.min(Result.time_seconds).label("best_time"),
        )
        .join(Result, Athlete.id == Result.athlete_id)
        .join(Event, Result.event_id == Event.id)
        .join(Meet, Event.meet_id == Meet.id)
        .filter(Result.disqualified == False)  # noqa: E712
        .filter(Result.time_seconds.isnot(None))
        .filter(Result.time_seconds > 0)
        .filter(Meet.meet_type.in_(["dual", "invitational", "exhibition"]))
        .filter(Event.event_type == "individual")
    )

    if seasons:
        query = query.filter(Meet.season.in_(seasons))

    query = query.group_by(
        Athlete.id,
        Athlete.full_name,
        Athlete.gender,
        Athlete.age_group,
        Athlete.age_group_lower,
        Athlete.age_group_upper,
        Event.distance,
        Event.stroke,
        Meet.season,
    )

    return pd.read_sql(query.statement, session.bind)


def compute_event_statistics(
    personal_bests_df: pd.DataFrame,
    standards_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compute per-standard statistics (percentiles, qual rate, P35 rec, etc.)."""
    if personal_bests_df.empty or standards_df.empty:
        return pd.DataFrame()

    results = []
    for _, std in standards_df.iterrows():
        subset = personal_bests_df[_in_band(personal_bests_df, std)]
        if len(subset) == 0:
            continue

        times = subset["best_time"]
        current_qt = std["standard_seconds"]

        stats = {
            "gender": std["gender"],
            "age_group": std["age_group"],
            "age_group_lower": std["age_group_lower"],
            "age_group_upper": std["age_group_upper"],
            "distance": std["distance"],
            "stroke": std["stroke"],
            "event_name": f"{'Girls' if std['gender'] == 'F' else 'Boys'} {std['age_group']} {std['distance']}m {std['stroke']}",
            "current_qt": current_qt,
            "current_qt_formatted": std["standard_formatted"],
            "n_swimmers": len(subset),
            "n_unique_swimmers": subset["swimmer_id"].nunique(),
            "mean": times.mean(),
            "median": times.median(),
            "std": times.std(),
            "min": times.min(),
            "max": times.max(),
            "p25": times.quantile(0.25),
            "p30": times.quantile(0.30),
            "p35": times.quantile(0.35),
            "p40": times.quantile(0.40),
            "p45": times.quantile(0.45),
            "p50": times.quantile(0.50),
            "p75": times.quantile(0.75),
            "qualifiers": (times <= current_qt).sum(),
            "qual_rate": (times <= current_qt).mean() * 100,
        }
        stats["delta_from_p35"] = stats["p35"] - current_qt
        results.append(stats)

    return pd.DataFrame(results)


def compute_yearly_statistics(
    personal_bests_df: pd.DataFrame,
    standards_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compute per-standard, per-year statistics for trend analysis."""
    if personal_bests_df.empty or standards_df.empty:
        return pd.DataFrame()

    results = []
    for _, std in standards_df.iterrows():
        subset = personal_bests_df[_in_band(personal_bests_df, std)]
        if len(subset) == 0:
            continue

        current_qt = std["standard_seconds"]
        event_name = f"{'Girls' if std['gender'] == 'F' else 'Boys'} {std['age_group']} {std['distance']}m {std['stroke']}"

        for season, season_df in subset.groupby("season"):
            times = season_df["best_time"]
            results.append({
                "gender": std["gender"],
                "age_group": std["age_group"],
                "distance": std["distance"],
                "stroke": std["stroke"],
                "event_name": event_name,
                "season": season,
                "current_qt": current_qt,
                "n_swimmers": len(season_df),
                "mean": times.mean(),
                "median": times.median(),
                "std": times.std(),
                "p25": times.quantile(0.25),
                "p35": times.quantile(0.35),
                "p50": times.quantile(0.50),
                "p75": times.quantile(0.75),
                "qualifiers": (times <= current_qt).sum(),
                "qual_rate": (times <= current_qt).mean() * 100,
            })

    return pd.DataFrame(results)


def get_times_for_event(
    personal_bests_df: pd.DataFrame,
    gender: str,
    age_group_lower: int,
    age_group_upper: int,
    distance: int,
    stroke: str,
) -> pd.DataFrame:
    """Get all personal-best times for a specific event standard (for histograms)."""
    mask = (
        (personal_bests_df["gender"] == gender)
        & (personal_bests_df["age_group_lower"] >= age_group_lower)
        & (personal_bests_df["age_group_upper"] <= age_group_upper)
        & (personal_bests_df["distance"] == distance)
        & (personal_bests_df["stroke"] == stroke)
    )
    return personal_bests_df[mask].copy()


def round_to_standard(seconds: float, precision: float = 0.25) -> float:
    """Round time to nearest precision (default 0.25s) for clean standard times."""
    if pd.isna(seconds) or seconds is None:
        return seconds
    return round(seconds / precision) * precision


def format_time(seconds: float) -> str:
    """Format seconds as MM:SS.ss or SS.ss."""
    if pd.isna(seconds) or seconds is None:
        return "N/A"
    mins, secs = divmod(seconds, 60)
    if mins > 0:
        return f"{int(mins)}:{secs:05.2f}"
    return f"{secs:.2f}"


def format_time_rounded(seconds: float, precision: float = 0.25) -> str:
    """Format time rounded to nearest precision for display as a standard."""
    return format_time(round_to_standard(seconds, precision))


def get_city_meet_participation(session: Session) -> pd.DataFrame:
    """Get City Meet participation counts grouped by standard criteria.

    Returns athlete counts per (gender, own age band, distance, stroke, season).
    """
    query = (
        session.query(
            Athlete.gender,
            Athlete.age_group,
            Athlete.age_group_lower,
            Athlete.age_group_upper,
            Event.distance,
            Event.stroke,
            Meet.season,
            func.count(func.distinct(Athlete.id)).label("cm_swimmers"),
        )
        .join(Result, Athlete.id == Result.athlete_id)
        .join(Event, Result.event_id == Event.id)
        .join(Meet, Event.meet_id == Meet.id)
        .filter(Meet.meet_type == "city_meet")
        .filter(Event.event_type == "individual")
        .filter(Result.time_seconds.isnot(None))
        .group_by(
            Athlete.gender,
            Athlete.age_group,
            Athlete.age_group_lower,
            Athlete.age_group_upper,
            Event.distance,
            Event.stroke,
            Meet.season,
        )
    )
    return pd.read_sql(query.statement, session.bind)


def get_cm_stats_by_standard(
    cm_participation_df: pd.DataFrame,
    standards_df: pd.DataFrame,
) -> pd.DataFrame:
    """Aggregate City Meet participation by standard (summing across bands within range)."""
    if cm_participation_df.empty or standards_df.empty:
        return pd.DataFrame()

    results = []
    for _, std in standards_df.iterrows():
        subset = cm_participation_df[_in_band(cm_participation_df, std)]
        if len(subset) == 0:
            continue

        event_name = f"{'Girls' if std['gender'] == 'F' else 'Boys'} {std['age_group']} {std['distance']}m {std['stroke']}"
        for season, season_df in subset.groupby("season"):
            results.append({
                "gender": std["gender"],
                "age_group": std["age_group"],
                "age_group_lower": std["age_group_lower"],
                "age_group_upper": std["age_group_upper"],
                "distance": std["distance"],
                "stroke": std["stroke"],
                "event_name": event_name,
                "season": season,
                "cm_swimmers": season_df["cm_swimmers"].sum(),
            })

    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# Trend projection & outlier detection
# ---------------------------------------------------------------------------

def compute_trend_projection(
    yearly_stats_df: pd.DataFrame,
    gender: str,
    age_group: str,
    distance: int,
    stroke: str,
    project_to_years: list[int] = None,
) -> dict:
    """Linear-regress yearly P35/median/mean and project forward."""
    if project_to_years is None:
        project_to_years = [2026, 2028, 2030]

    event_yearly = yearly_stats_df[
        (yearly_stats_df["gender"] == gender)
        & (yearly_stats_df["age_group"] == age_group)
        & (yearly_stats_df["distance"] == distance)
        & (yearly_stats_df["stroke"] == stroke)
    ].sort_values("season")

    result = {
        "slope_p35": None, "slope_median": None, "slope_mean": None,
        "r_squared": None, "confidence": "insufficient", "projections": [],
    }

    if len(event_yearly) < 2:
        for yr in project_to_years:
            result["projections"].append({
                "year": yr, "projected_p35": None,
                "projected_median": None, "projected_mean": None,
            })
        return result

    x = event_yearly["season"].values.astype(float)
    p35_vals = event_yearly["p35"].values
    median_vals = event_yearly["median"].values
    mean_vals = event_yearly["mean"].values

    coeffs_p35 = np.polyfit(x, p35_vals, 1)
    coeffs_median = np.polyfit(x, median_vals, 1)
    coeffs_mean = np.polyfit(x, mean_vals, 1)

    result["slope_p35"] = coeffs_p35[0]
    result["slope_median"] = coeffs_median[0]
    result["slope_mean"] = coeffs_mean[0]

    predicted = np.polyval(coeffs_p35, x)
    ss_res = np.sum((p35_vals - predicted) ** 2)
    ss_tot = np.sum((p35_vals - np.mean(p35_vals)) ** 2)
    result["r_squared"] = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

    if len(event_yearly) < 3:
        result["confidence"] = "weak"
    elif result["r_squared"] >= 0.5:
        result["confidence"] = "strong"
    else:
        result["confidence"] = "weak"

    for yr in project_to_years:
        result["projections"].append({
            "year": yr,
            "projected_p35": np.polyval(coeffs_p35, yr),
            "projected_median": np.polyval(coeffs_median, yr),
            "projected_mean": np.polyval(coeffs_mean, yr),
        })

    return result


def detect_statistical_outliers(
    personal_bests_df: pd.DataFrame,
    gender: str,
    age_group_lower: int,
    age_group_upper: int,
    distance: int,
    stroke: str,
    threshold: float = 1.5,
) -> pd.DataFrame:
    """Flag swimmers whose best time is > threshold std devs below the mean."""
    event_times = get_times_for_event(
        personal_bests_df, gender, age_group_lower, age_group_upper, distance, stroke
    )
    if event_times.empty:
        return event_times

    swimmer_bests = event_times.groupby("swimmer_id").agg(
        best_time=("best_time", "min"),
        full_name=("full_name", "first"),
    ).reset_index()

    mean_time = swimmer_bests["best_time"].mean()
    std_time = swimmer_bests["best_time"].std()

    if std_time == 0 or pd.isna(std_time):
        swimmer_bests["z_score"] = 0.0
        swimmer_bests["is_outlier"] = False
    else:
        swimmer_bests["z_score"] = (swimmer_bests["best_time"] - mean_time) / std_time
        swimmer_bests["is_outlier"] = swimmer_bests["z_score"] < -threshold

    return swimmer_bests


def detect_topn_outliers(
    personal_bests_df: pd.DataFrame,
    gender: str,
    age_group_lower: int,
    age_group_upper: int,
    distance: int,
    stroke: str,
    n: int = 5,
) -> pd.DataFrame:
    """Flag top N fastest swimmers per event."""
    event_times = get_times_for_event(
        personal_bests_df, gender, age_group_lower, age_group_upper, distance, stroke
    )
    if event_times.empty:
        return event_times

    swimmer_bests = event_times.groupby("swimmer_id").agg(
        best_time=("best_time", "min"),
        full_name=("full_name", "first"),
    ).reset_index().sort_values("best_time")

    swimmer_bests["is_topn_outlier"] = False
    if len(swimmer_bests) > 0:
        swimmer_bests.iloc[:min(n, len(swimmer_bests)),
                           swimmer_bests.columns.get_loc("is_topn_outlier")] = True

    return swimmer_bests


def filter_excluded_swimmers(
    personal_bests_df: pd.DataFrame,
    excluded_ids: set,
    statistical_ids: set,
    topn_ids: set,
    use_statistical: bool,
    use_topn: bool,
    use_manual: bool,
) -> pd.DataFrame:
    """Apply selected exclusion methods and return the filtered DataFrame."""
    ids_to_exclude = set()
    if use_manual:
        ids_to_exclude |= excluded_ids
    if use_statistical:
        ids_to_exclude |= statistical_ids
    if use_topn:
        ids_to_exclude |= topn_ids

    if ids_to_exclude:
        return personal_bests_df[~personal_bests_df["swimmer_id"].isin(ids_to_exclude)].copy()
    return personal_bests_df.copy()


def compute_qual_rate_at_time(times: pd.Series, custom_time: float) -> tuple[float, int]:
    """Given times and a hypothetical QT, return (qual %, count)."""
    if times.empty:
        return 0.0, 0
    qualifiers = (times <= custom_time).sum()
    return qualifiers / len(times) * 100, int(qualifiers)


def compute_time_for_target_rate(times: pd.Series, target_pct: float) -> float:
    """Given times and target %, return the time threshold (percentile lookup)."""
    if times.empty:
        return 0.0
    return float(times.quantile(target_pct / 100.0))


def compute_capped_projection(
    swimmer_bests: pd.Series,
    current_p35: float,
    slope: float,
    years_forward: float,
    min_rate: float = 28.0,
    max_rate: float = 45.0,
) -> tuple[float, str]:
    """Trend-adjusted QT recommendation with qual-rate guardrails."""
    base_qt = round_to_standard(current_p35)

    raw_adjustment = slope * years_forward
    max_adjustment = abs(current_p35 - swimmer_bests.median()) * 0.5
    capped_adjustment = max(-max_adjustment, min(max_adjustment, raw_adjustment))
    candidate_qt = round_to_standard(current_p35 + capped_adjustment)

    candidate_rate, _ = compute_qual_rate_at_time(swimmer_bests, candidate_qt)
    if candidate_rate < min_rate:
        return base_qt, "capped at floor"
    if candidate_rate > max_rate:
        ceiling_qt = round_to_standard(float(swimmer_bests.quantile(max_rate / 100.0)))
        return ceiling_qt, "capped at ceiling"
    return candidate_qt, "trend-adjusted"
