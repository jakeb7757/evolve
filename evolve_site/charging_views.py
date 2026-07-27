import csv
from collections import OrderedDict

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import cache_page

from .charging_index.config import (
    POWER_BUCKETS,
    SCORING_CONFIG,
    SCORING_VERSION,
    SITE_SIZE_BUCKETS,
)
from .models import (
    ChargingDataImport,
    ChargingNetworkMetricSnapshot,
    ChargingStationSnapshot,
)


SORT_FIELDS = OrderedDict(
    (
        ("score", ("Infrastructure score", "infrastructure_score")),
        ("locations", ("Locations", "site_count")),
        ("ports", ("Ports", "dc_fast_port_count")),
        ("average-site-size", ("Average ports/site", "average_ports_per_site")),
        ("states", ("States covered", "states_covered")),
        ("large-sites", ("Large-site share", "large_site_percentage")),
        ("high-power", ("High-power share", "high_power_site_percentage")),
    )
)
COMPONENT_NAMES = {
    "geographic_coverage": "Geographic coverage",
    "total_ports": "Total ports",
    "average_site_size": "Average site size",
    "large_site_share": "Large-site share",
    "high_power_share": "High-power share",
    "connector_support": "Connector support",
}
STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia",
}


def production_cache(seconds):
    def decorator(view):
        return view if settings.DEBUG else cache_page(seconds)(view)

    return decorator


def _active_import():
    return (
        ChargingDataImport.objects.filter(
            status=ChargingDataImport.Status.SUCCEEDED, is_active=True
        )
        .prefetch_related("network_metrics__network")
        .first()
    )


def _sort_metrics(metrics, sort_key, direction):
    field_name = SORT_FIELDS[sort_key][1]

    def sort_value(metric):
        value = getattr(metric, field_name)
        return float(value) if value is not None else float("-inf")

    return sorted(metrics, key=sort_value, reverse=direction == "desc")


def _freshness_context(data_import):
    return {
        "snapshot_date": data_import.snapshot_date,
        "source_last_updated_at": data_import.source_last_updated_at,
        "imported_at": data_import.completed_at,
        "scoring_version": data_import.scoring_version,
    }


@production_cache(15 * 60)
def charging_network_leaderboard(request, *, embed=False):
    data_import = _active_import()
    if not data_import:
        return render(
            request,
            "evolve_site/charging_networks/leaderboard.html",
            {"data_unavailable": True, "embed": embed},
        )
    sort_key = request.GET.get("sort", "score")
    if sort_key not in SORT_FIELDS:
        sort_key = "score"
    direction = request.GET.get("direction", "desc")
    if direction not in {"asc", "desc"}:
        direction = "desc"

    metrics = list(data_import.network_metrics.all())
    scored = _sort_metrics(
        [metric for metric in metrics if metric.is_scored], sort_key, direction
    )
    emerging = sorted(
        [metric for metric in metrics if not metric.is_scored and metric.site_count],
        key=lambda metric: metric.site_count,
        reverse=True,
    )
    headers = []
    for key, (label, _) in SORT_FIELDS.items():
        is_current = key == sort_key
        next_direction = "asc" if is_current and direction == "desc" else "desc"
        headers.append(
            {
                "key": key,
                "label": label,
                "is_current": is_current,
                "direction": direction if is_current else None,
                "url": f"?sort={key}&direction={next_direction}",
            }
        )
    return render(
        request,
        "evolve_site/charging_networks/leaderboard.html",
        {
            **_freshness_context(data_import),
            "data_import": data_import,
            "scored_metrics": scored,
            "emerging_metrics": emerging,
            "headers": headers,
            "sort_label": SORT_FIELDS[sort_key][0],
            "sort_direction": direction,
            "minimum_scored_sites": SCORING_CONFIG["thresholds"][
                "minimum_scored_sites"
            ],
            "embed": embed,
        },
    )


def charging_network_embed(request):
    return charging_network_leaderboard(request, embed=True)


def _distribution_rows(distribution, definitions, total):
    return [
        {
            "key": key,
            "label": label,
            "count": distribution.get(key, 0),
            "percentage": distribution.get(key, 0) / total * 100 if total else 0,
        }
        for key, label in definitions
    ]


def _component_rows(metric):
    rows = []
    for key, component in metric.score_components.items():
        raw = component["raw"]
        if key == "total_ports":
            raw_display = f"{int(raw):,} ports"
        elif key == "average_site_size":
            raw_display = f"{float(raw):.1f} ports/site"
        elif key == "connector_support":
            raw_display = (
                ", ".join(raw.get("types") or []) or "No usable data"
                if isinstance(raw, dict)
                else str(raw)
            )
        else:
            raw_display = "Unknown" if raw is None else f"{float(raw):.1f}%"
        rows.append(
            {
                "name": COMPONENT_NAMES[key],
                "raw": raw_display,
                "score": float(component["score"]),
                "weight": float(component["weight"]) * 100,
                "contribution": float(component["weighted_contribution"]),
            }
        )
    return rows


def _connector_rows(metric):
    connector_counts = (
        ("CCS", metric.ccs_connector_count),
        ("J3400 / NACS", metric.j3400_connector_count),
        ("CHAdeMO", metric.chademo_connector_count),
        ("MCS / J3271", metric.mcs_connector_count),
    )
    total = sum(count for _, count in connector_counts)
    return [
        {
            "name": name,
            "count": count,
            "percentage": count / total * 100 if total else 0,
        }
        for name, count in connector_counts
    ]


def _network_summary(metric, all_metrics):
    scored = [item for item in all_metrics if item.is_scored]
    average_size = (
        sum(float(item.average_ports_per_site) for item in scored) / len(scored)
        if scored
        else 0
    )
    strengths = []
    limitations = []
    if metric.states_covered >= 35:
        strengths.append("broad geographic coverage")
    elif metric.states_covered <= 10:
        limitations.append("a geographically concentrated footprint")
    if float(metric.average_ports_per_site) >= average_size and average_size:
        strengths.append("above-average site size")
    if float(metric.large_site_percentage) >= 50:
        strengths.append("a high share of eight-port-or-larger sites")
    if float(metric.power_data_coverage) < 60:
        limitations.append(
            "incomplete listed power data, so the high-power score needs caution"
        )
    if not strengths:
        strengths.append("a measurable public DC-fast footprint")
    if not limitations:
        limitations.append(
            "no measurement of reliability, pricing, congestion, or live availability"
        )
    return {"strengths": strengths, "limitations": limitations}


@production_cache(15 * 60)
def charging_network_detail(request, slug):
    data_import = _active_import()
    if not data_import:
        raise Http404("No active Charging Network Index snapshot")
    try:
        metric = data_import.network_metrics.select_related("network").get(
            network__slug=slug
        )
    except ChargingNetworkMetricSnapshot.DoesNotExist as exc:
        raise Http404("Charging network not found") from exc
    stations = ChargingStationSnapshot.objects.filter(
        data_import=data_import, network=metric.network
    )
    state_rows = sorted(
        [
            {
                "code": code,
                "name": name,
                "site_count": metric.state_counts.get(code, 0),
            }
            for code, name in STATE_NAMES.items()
        ],
        key=lambda row: (-row["site_count"], row["name"]),
    )
    all_metrics = list(data_import.network_metrics.all())
    return render(
        request,
        "evolve_site/charging_networks/detail.html",
        {
            **_freshness_context(data_import),
            "data_import": data_import,
            "metric": metric,
            "component_rows": _component_rows(metric),
            "connector_rows": _connector_rows(metric),
            "site_distribution": _distribution_rows(
                metric.site_size_distribution, SITE_SIZE_BUCKETS, metric.site_count
            ),
            "power_distribution": _distribution_rows(
                metric.power_distribution, POWER_BUCKETS, metric.site_count
            ),
            "state_rows": state_rows,
            "largest_sites": stations.order_by(
                "-dc_fast_port_count", "station_name"
            )[:10],
            "summary": _network_summary(metric, all_metrics),
        },
    )


@production_cache(24 * 60 * 60)
def charging_network_methodology(request):
    return render(
        request,
        "evolve_site/charging_networks/methodology.html",
        {
            "scoring_version": SCORING_VERSION,
            "weights": [
                (COMPONENT_NAMES[key], value * 100)
                for key, value in SCORING_CONFIG["weights"].items()
            ],
            "thresholds": SCORING_CONFIG["thresholds"],
        },
    )


@production_cache(60 * 60)
def charging_network_export(request):
    data_import = _active_import()
    if not data_import:
        raise Http404("No active Charging Network Index snapshot")
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"evolve-charging-network-index-{data_import.snapshot_date}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(
        (
            "snapshot_date", "network_key", "network_name", "site_count",
            "dc_fast_port_count", "average_ports_per_site",
            "median_ports_per_site", "large_site_percentage", "states_covered",
            "state_coverage_percentage", "high_power_site_percentage",
            "ultra_high_power_site_percentage", "power_data_coverage",
            "ccs_connector_count", "j3400_connector_count",
            "chademo_connector_count", "mcs_connector_count",
            "infrastructure_score", "infrastructure_grade", "scoring_version",
            "source_last_updated_at", "source_network_last_import_date",
        )
    )
    for metric in data_import.network_metrics.select_related("network").order_by(
        "-infrastructure_score", "network__name"
    ):
        writer.writerow(
            (
                data_import.snapshot_date, metric.network.network_key,
                metric.network.name, metric.site_count, metric.dc_fast_port_count,
                metric.average_ports_per_site, metric.median_ports_per_site,
                metric.large_site_percentage, metric.states_covered,
                metric.state_coverage_percentage,
                metric.high_power_site_percentage,
                metric.ultra_high_power_site_percentage,
                metric.power_data_coverage, metric.ccs_connector_count,
                metric.j3400_connector_count, metric.chademo_connector_count,
                metric.mcs_connector_count, metric.infrastructure_score,
                metric.infrastructure_grade, data_import.scoring_version,
                data_import.source_last_updated_at,
                metric.source_network_last_import_date,
            )
        )
    return response
