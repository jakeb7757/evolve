import logging
import time
from collections import defaultdict
from datetime import date, datetime, time as datetime_time
from decimal import Decimal

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from evolve_site.models import (
    ChargingDataImport,
    ChargingNetwork,
    ChargingNetworkMetricSnapshot,
    ChargingStationSnapshot,
)

from .config import (
    INCLUDED_NETWORKS,
    NETWORK_CONFIG_BY_KEY,
    SCHEMA_VERSION,
    SCORING_CONFIG,
    SCORING_VERSION,
    validate_scoring_config,
)
from .parser import parse_station_csv
from .scoring import aggregate_network, score_networks


logger = logging.getLogger(__name__)
BASE_URL = "https://developer.nlr.gov/api/alt-fuel-stations/v1"


class ChargingImportError(RuntimeError):
    pass


class NLRChargingClient:
    def __init__(self, api_key: str, *, timeout: tuple[int, int] = (10, 120)):
        if not api_key:
            raise ChargingImportError(
                "NLR_API_KEY is required. Add it to the environment before refreshing."
            )
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.75,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def _get(self, path: str, *, params: dict | None = None) -> requests.Response:
        safe_params = dict(params or {})
        response = self.session.get(
            f"{BASE_URL}/{path}",
            params=safe_params,
            headers={"X-Api-Key": self.api_key},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response

    def fetch_network_catalog(self) -> list[dict]:
        payload = self._get(
            "electric-networks.json",
            params={"country": "US", "include_inactive": "true"},
        ).json()
        if not isinstance(payload, list):
            raise ChargingImportError("NLR network catalog returned an unexpected shape.")
        return [item for item in payload if item.get("key") not in (None, "all")]

    def fetch_last_updated(self) -> str:
        payload = self._get("last-updated.json").json()
        value = payload.get("last_updated")
        if not value:
            raise ChargingImportError("NLR last-updated response did not contain a date.")
        return value

    def fetch_charging_units_csv(self, network_keys: list[str] | None = None) -> str:
        network_keys = network_keys or list(NETWORK_CONFIG_BY_KEY)
        response = self._get(
            "ev-charging-units.csv",
            params={
                "country": "US",
                "access": "public",
                "status": "E",
                "ev_charging_level": "dc_fast",
                "ev_network": ",".join(network_keys),
                "limit": "all",
            },
        )
        if not response.content.strip():
            raise ChargingImportError("NLR charging-unit export was empty.")
        return response.content.decode("utf-8-sig")


def _catalog_date(value) -> date | None:
    return parse_date(value) if value else None


def _source_datetime(value):
    parsed = parse_datetime(value)
    if parsed is None:
        parsed_date = parse_date(value)
        if parsed_date:
            parsed = timezone.make_aware(
                datetime.combine(parsed_date, datetime_time.min)
            )
    return parsed


def _network_defaults(config, catalog_item: dict | None) -> dict:
    catalog_item = catalog_item or {}
    return {
        "slug": config.slug,
        "name": config.display_name or catalog_item.get("name") or config.key,
        "short_name": config.short_name or "",
        "network_url": catalog_item.get("url") or "",
        "import_type": catalog_item.get("import_type") or "",
        "source_last_import_date": _catalog_date(
            catalog_item.get("last_import_date")
        ),
        "is_active": bool(catalog_item) and not bool(catalog_item.get("date_removed")),
        "is_included": True,
        "include_in_leaderboard": config.include_in_leaderboard,
        "minimum_site_count": config.minimum_site_count,
        "notes": config.notes,
    }


def _station_model(station, data_import, network, snapshot_date):
    return ChargingStationSnapshot(
        data_import=data_import,
        snapshot_date=snapshot_date,
        station_id=station.station_id,
        network=network,
        station_name=station.station_name or "",
        street_address=station.street_address or "",
        city=station.city or "",
        state=station.state or "",
        zip=station.zip_code or "",
        latitude=station.latitude,
        longitude=station.longitude,
        status_code=station.status_code or "",
        access_code=station.access_code or "",
        facility_type=station.facility_type or "",
        dc_fast_port_count=station.dc_fast_port_count,
        ccs_connector_count=station.ccs_connector_count,
        chademo_connector_count=station.chademo_connector_count,
        j3400_connector_count=station.j3400_connector_count,
        mcs_connector_count=station.mcs_connector_count,
        ccs_power_kw_values=station.ccs_power_kw_values,
        chademo_power_kw_values=station.chademo_power_kw_values,
        j3400_power_kw_values=station.j3400_power_kw_values,
        mcs_power_kw_values=station.mcs_power_kw_values,
        max_power_kw=(
            Decimal(str(station.max_power_kw))
            if station.max_power_kw is not None
            else None
        ),
    )


def _metric_model(metric, data_import, network, snapshot_date):
    decimal_fields = {
        "average_ports_per_site",
        "median_ports_per_site",
        "large_site_percentage",
        "state_coverage_percentage",
        "high_power_site_percentage",
        "ultra_high_power_site_percentage",
        "power_data_coverage",
        "infrastructure_score",
        "infrastructure_score_unrounded",
    }
    values = {}
    model_fields = {
        field.name
        for field in ChargingNetworkMetricSnapshot._meta.fields
        if field.name not in {"id", "data_import", "network", "snapshot_date"}
    }
    for name in model_fields:
        if name == "source_network_last_import_date":
            values[name] = network.source_last_import_date
        elif name in metric:
            value = metric[name]
            values[name] = (
                Decimal(str(value))
                if name in decimal_fields and value is not None
                else value
            )
    return ChargingNetworkMetricSnapshot(
        data_import=data_import,
        snapshot_date=snapshot_date,
        network=network,
        **values,
    )


def _validate_snapshot(metrics: list[dict], prior_site_count: int, allow_large_decrease):
    if not metrics or not any(metric["site_count"] for metric in metrics):
        raise ChargingImportError("No included networks had station data.")
    total_sites = sum(metric["site_count"] for metric in metrics)
    if prior_site_count:
        decrease = (prior_site_count - total_sites) / prior_site_count * 100
        threshold = SCORING_CONFIG["thresholds"][
            "suspicious_site_decrease_percentage"
        ]
        if decrease > threshold and not allow_large_decrease:
            raise ChargingImportError(
                f"Normalized site count fell {decrease:.1f}% from the active snapshot; "
                "rerun with --allow-large-decrease after verifying the source."
            )
    for metric in metrics:
        if metric["dc_fast_port_count"] < 0:
            raise ChargingImportError("A network produced a negative port count.")
        score = metric["infrastructure_score"]
        if score is not None and not 0 <= score <= 100:
            raise ChargingImportError("A network score fell outside the 0–100 range.")


def refresh_charging_networks(
    *,
    client: NLRChargingClient | None = None,
    allow_large_decrease: bool = False,
) -> ChargingDataImport:
    """Fetch, validate, persist, and atomically activate a complete NLR snapshot."""
    started = time.monotonic()
    validate_scoring_config()
    import_record = ChargingDataImport.objects.create(
        status=ChargingDataImport.Status.RUNNING,
        started_at=timezone.now(),
        schema_version=SCHEMA_VERSION,
        scoring_version=SCORING_VERSION,
    )
    try:
        api_key = getattr(settings, "NLR_API_KEY", None)
        client = client or NLRChargingClient(api_key)
        catalog = client.fetch_network_catalog()
        catalog_at = timezone.now()
        catalog_by_key = {item["key"]: item for item in catalog if item.get("key")}
        missing_keys = sorted(set(NETWORK_CONFIG_BY_KEY) - set(catalog_by_key))
        valid_network_keys = [
            config.key
            for config in INCLUDED_NETWORKS
            if config.key in catalog_by_key
            and not catalog_by_key[config.key].get("date_removed")
        ]
        if not valid_network_keys:
            raise ChargingImportError(
                "None of the configured network keys are active in the NLR catalog."
            )
        source_last_updated = _source_datetime(client.fetch_last_updated())
        if source_last_updated is None:
            raise ChargingImportError("NLR returned an invalid dataset update date.")
        stations, report = parse_station_csv(
            client.fetch_charging_units_csv(valid_network_keys),
            known_network_keys=set(catalog_by_key),
        )
        if report.source_rows == 0:
            raise ChargingImportError("NLR charging-unit export had no data rows.")
        report.configured_networks_missing_from_catalog = missing_keys

        station_groups = defaultdict(list)
        for station in stations:
            station_groups[station.network_key].append(station)
        metrics = []
        for config in INCLUDED_NETWORKS:
            if not config.include_in_leaderboard:
                continue
            metric = aggregate_network(station_groups.get(config.key, []))
            metric["network_key"] = config.key
            metric["minimum_scored_sites"] = (
                config.minimum_site_count
                or SCORING_CONFIG["thresholds"]["minimum_scored_sites"]
            )
            metrics.append(metric)
        score_networks(metrics)
        snapshot_date = source_last_updated.date()
        included_network_count = sum(bool(group) for group in station_groups.values())
        import_record.snapshot_date = snapshot_date
        import_record.source_last_updated_at = source_last_updated
        import_record.source_network_catalog_at = catalog_at
        import_record.source_row_count = report.source_rows
        import_record.normalized_station_count = len(stations)
        import_record.included_network_count = included_network_count
        import_record.warnings = report.as_dict()
        import_record.save(
            update_fields=(
                "snapshot_date",
                "source_last_updated_at",
                "source_network_catalog_at",
                "source_row_count",
                "normalized_station_count",
                "included_network_count",
                "warnings",
            )
        )

        prior = (
            ChargingDataImport.objects.filter(
                status=ChargingDataImport.Status.SUCCEEDED, is_active=True
            )
            .prefetch_related("network_metrics")
            .first()
        )
        prior_sites = (
            sum(metric.site_count for metric in prior.network_metrics.all())
            if prior
            else 0
        )
        _validate_snapshot(metrics, prior_sites, allow_large_decrease)

        with transaction.atomic():
            network_models = {}
            for config in INCLUDED_NETWORKS:
                network, _ = ChargingNetwork.objects.update_or_create(
                    network_key=config.key,
                    defaults=_network_defaults(config, catalog_by_key.get(config.key)),
                )
                network_models[config.key] = network

            ChargingStationSnapshot.objects.bulk_create(
                [
                    _station_model(
                        station,
                        import_record,
                        network_models[station.network_key],
                        snapshot_date,
                    )
                    for station in stations
                ],
                batch_size=1000,
            )
            metric_by_key = {metric["network_key"]: metric for metric in metrics}
            ChargingNetworkMetricSnapshot.objects.bulk_create(
                [
                    _metric_model(
                        metric_by_key[config.key],
                        import_record,
                        network_models[config.key],
                        snapshot_date,
                    )
                    for config in INCLUDED_NETWORKS
                    if config.include_in_leaderboard
                ]
            )
            ChargingDataImport.objects.filter(is_active=True).update(is_active=False)
            import_record.status = ChargingDataImport.Status.SUCCEEDED
            import_record.completed_at = timezone.now()
            import_record.snapshot_date = snapshot_date
            import_record.source_last_updated_at = source_last_updated
            import_record.source_network_catalog_at = catalog_at
            import_record.source_row_count = report.source_rows
            import_record.normalized_station_count = len(stations)
            import_record.included_network_count = included_network_count
            import_record.warnings = report.as_dict()
            import_record.is_active = True
            import_record.save()

        logger.info(
            "Charging index refresh succeeded: rows=%d stations=%d networks=%d "
            "duration_seconds=%.2f",
            report.source_rows,
            len(stations),
            import_record.included_network_count,
            time.monotonic() - started,
        )
        return import_record
    except Exception as exc:
        import_record.status = ChargingDataImport.Status.FAILED
        import_record.completed_at = timezone.now()
        import_record.error_message = str(exc)[:4000]
        import_record.is_active = False
        import_record.save(
            update_fields=(
                "status",
                "completed_at",
                "error_message",
                "is_active",
            )
        )
        logger.exception(
            "Charging index refresh failed after %.2f seconds",
            time.monotonic() - started,
        )
        raise
