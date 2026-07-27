import math
import statistics
from collections import Counter

from .config import (
    POWER_BUCKETS,
    SCORING_CONFIG,
    SITE_SIZE_BUCKETS,
    US_STATES_AND_DC,
    validate_scoring_config,
)


def grade_for_score(score: float) -> str:
    if score >= 90:
        return "S"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    if score >= 50:
        return "D"
    return "F"


def _site_size_bucket(port_count: int) -> str:
    if port_count <= 2:
        return "1-2"
    if port_count <= 4:
        return "3-4"
    if port_count <= 7:
        return "5-7"
    if port_count <= 11:
        return "8-11"
    if port_count <= 19:
        return "12-19"
    return "20+"


def _power_bucket(power: float | None) -> str:
    if power is None:
        return "unknown"
    if power < 50:
        return "below-50"
    if power < 150:
        return "50-149"
    if power < 250:
        return "150-249"
    if power < 350:
        return "250-349"
    return "350+"


def aggregate_network(stations: list) -> dict:
    thresholds = SCORING_CONFIG["thresholds"]
    site_count = len(stations)
    port_counts = [station.dc_fast_port_count for station in stations]
    port_count = sum(port_counts)
    known_power = [station for station in stations if station.max_power_kw is not None]
    high_power_count = sum(
        station.max_power_kw >= thresholds["high_power_kw"] for station in known_power
    )
    ultra_high_power_count = sum(
        station.max_power_kw >= thresholds["ultra_high_power_kw"]
        for station in known_power
    )
    states = sorted(
        {station.state for station in stations if station.state in US_STATES_AND_DC}
    )
    territories = sorted(
        {
            station.state
            for station in stations
            if station.state and station.state not in US_STATES_AND_DC
        }
    )
    state_counts = Counter(station.state for station in stations if station.state)
    site_buckets = Counter(_site_size_bucket(count) for count in port_counts)
    power_buckets = Counter(_power_bucket(station.max_power_kw) for station in stations)
    large_site_count = sum(
        count >= thresholds["large_site_ports"] for count in port_counts
    )

    def percentage(numerator: int, denominator: int) -> float | None:
        return numerator / denominator * 100 if denominator else None

    return {
        "site_count": site_count,
        "dc_fast_port_count": port_count,
        "average_ports_per_site": port_count / site_count if site_count else 0,
        "median_ports_per_site": statistics.median(port_counts) if port_counts else 0,
        "small_site_count": site_count - large_site_count,
        "large_site_count": large_site_count,
        "large_site_percentage": percentage(large_site_count, site_count) or 0,
        "states_covered": len(states),
        "state_coverage_percentage": len(states) / 51 * 100,
        "territories_covered": territories,
        "state_counts": dict(sorted(state_counts.items())),
        "high_power_site_count": high_power_count,
        "high_power_site_percentage": percentage(high_power_count, len(known_power)),
        "ultra_high_power_site_count": ultra_high_power_count,
        "ultra_high_power_site_percentage": percentage(
            ultra_high_power_count, len(known_power)
        ),
        "power_data_coverage": percentage(len(known_power), site_count) or 0,
        "ccs_connector_count": sum(s.ccs_connector_count for s in stations),
        "chademo_connector_count": sum(s.chademo_connector_count for s in stations),
        "j3400_connector_count": sum(s.j3400_connector_count for s in stations),
        "mcs_connector_count": sum(s.mcs_connector_count for s in stations),
        "connector_types_supported": [
            name
            for name, field in (
                ("CCS", "ccs_connector_count"),
                ("J3400/NACS", "j3400_connector_count"),
                ("CHAdeMO", "chademo_connector_count"),
                ("MCS", "mcs_connector_count"),
            )
            if any(getattr(station, field) for station in stations)
        ],
        "site_size_distribution": {
            key: site_buckets.get(key, 0) for key, _ in SITE_SIZE_BUCKETS
        },
        "power_distribution": {
            key: power_buckets.get(key, 0) for key, _ in POWER_BUCKETS
        },
    }


def connector_support_score(metric: dict) -> tuple[float, int]:
    thresholds = SCORING_CONFIG["thresholds"]
    share_count = math.ceil(
        metric["dc_fast_port_count"]
        * thresholds["meaningful_connector_share_percentage"]
        / 100
    )
    meaningful_count = max(
        1, min(share_count, thresholds["meaningful_connector_count_cap"])
    )
    ccs = metric["ccs_connector_count"] >= meaningful_count
    j3400 = metric["j3400_connector_count"] >= meaningful_count
    chademo = metric["chademo_connector_count"] >= meaningful_count
    if ccs and j3400:
        return 100.0, meaningful_count
    if ccs or j3400:
        return 70.0, meaningful_count
    if chademo:
        return 20.0, meaningful_count
    return 0.0, meaningful_count


def score_networks(metrics: list[dict]) -> list[dict]:
    validate_scoring_config()
    thresholds = SCORING_CONFIG["thresholds"]
    weights = SCORING_CONFIG["weights"]
    eligible = [
        metric
        for metric in metrics
        if metric["site_count"]
        >= metric.get("minimum_scored_sites", thresholds["minimum_scored_sites"])
    ]
    max_ports = max((metric["dc_fast_port_count"] for metric in eligible), default=0)

    for metric in metrics:
        metric["is_scored"] = metric["site_count"] >= metric.get(
            "minimum_scored_sites", thresholds["minimum_scored_sites"]
        )
        geographic = min(metric["state_coverage_percentage"], 100)
        ports = (
            math.log1p(metric["dc_fast_port_count"]) / math.log1p(max_ports) * 100
            if max_ports
            else 0
        )
        site_size = min(
            metric["average_ports_per_site"]
            / thresholds["average_site_size_target"],
            1,
        ) * 100
        large_share = min(metric["large_site_percentage"], 100)
        high_power_raw = metric["high_power_site_percentage"] or 0
        confidence = min(
            metric["power_data_coverage"]
            / thresholds["power_confidence_target_percentage"],
            1,
        )
        high_power = high_power_raw * confidence
        connector, meaningful_count = connector_support_score(metric)
        raw_values = {
            "geographic_coverage": metric["state_coverage_percentage"],
            "total_ports": metric["dc_fast_port_count"],
            "average_site_size": metric["average_ports_per_site"],
            "large_site_share": metric["large_site_percentage"],
            "high_power_share": metric["high_power_site_percentage"],
            "connector_support": {
                "types": metric["connector_types_supported"],
                "meaningful_count": meaningful_count,
            },
        }
        scores = {
            "geographic_coverage": geographic,
            "total_ports": ports,
            "average_site_size": site_size,
            "large_site_share": large_share,
            "high_power_share": high_power,
            "connector_support": connector,
        }
        components = {}
        for name, score in scores.items():
            components[name] = {
                "raw": raw_values[name],
                "score": score,
                "weight": weights[name],
                "weighted_contribution": score * weights[name],
            }
        unrounded_score = sum(
            component["weighted_contribution"] for component in components.values()
        )
        public_score = round(unrounded_score, 1)
        metric["score_components"] = components
        metric["infrastructure_score_unrounded"] = unrounded_score
        metric["infrastructure_score"] = (
            public_score if metric["is_scored"] else None
        )
        metric["infrastructure_grade"] = (
            grade_for_score(public_score) if metric["is_scored"] else ""
        )
    return metrics
