from datetime import date
from pathlib import Path

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .charging_index.config import (
    INCLUDED_NETWORKS,
    NETWORK_CONFIG_BY_KEY,
    SCORING_CONFIG,
    validate_scoring_config,
)
from .charging_index.importer import ChargingImportError, refresh_charging_networks
from .charging_index.parser import StationRecord, parse_power_values, parse_station_csv
from .charging_index.scoring import (
    aggregate_network,
    grade_for_score,
    score_networks,
)
from .models import (
    ChargingDataImport,
    ChargingNetwork,
    ChargingNetworkMetricSnapshot,
)


FIXTURE_PATH = Path(__file__).parent / "test_fixtures" / "charging_units.csv"


def fixture_csv():
    return FIXTURE_PATH.read_text(encoding="utf-8")


class ParserTests(TestCase):
    def test_numeric_null_and_structured_power_parsing(self):
        self.assertEqual(parse_power_values("150, 250 kW / 350"), [150.0, 250.0, 350.0])
        self.assertEqual(parse_power_values(""), [])
        self.assertEqual(parse_power_values(None), [])

    def test_groups_by_station_and_does_not_repeat_station_port_totals(self):
        stations, report = parse_station_csv(fixture_csv())
        alpha = next(station for station in stations if station.station_id == "1001")

        self.assertEqual(alpha.dc_fast_port_count, 8)
        self.assertEqual(alpha.ccs_connector_count, 2)
        self.assertEqual(alpha.ccs_power_kw_values, [150.0, 250.0, 350.0])
        self.assertEqual(alpha.max_power_kw, 350.0)
        self.assertEqual(report.source_rows, 11)
        self.assertEqual(report.missing_station_id_rows, 1)
        self.assertEqual(report.unknown_network_key_rows, 1)
        self.assertEqual(report.excluded_status_rows, 2)

    def test_normalizes_state_and_preserves_missing_power(self):
        stations, report = parse_station_csv(fixture_csv())
        beta = next(station for station in stations if station.station_id == "1002")
        missing_power = next(
            station for station in stations if station.station_id == "1004"
        )

        self.assertEqual(beta.state, "TX")
        self.assertIsNone(missing_power.max_power_kw)
        self.assertGreaterEqual(report.missing_power_stations, 1)
        self.assertEqual(report.missing_state_stations, 1)
        self.assertEqual(report.zero_or_missing_port_stations, 1)


class AggregationAndScoringTests(TestCase):
    def station(self, station_id, ports, state, power, **connectors):
        return StationRecord(
            station_id=str(station_id),
            network_key="Tesla",
            state=state,
            dc_fast_port_count=ports,
            max_power_kw=power,
            ccs_connector_count=connectors.get("ccs", 0),
            j3400_connector_count=connectors.get("j3400", 0),
            chademo_connector_count=connectors.get("chademo", 0),
        )

    def test_aggregation_metrics_use_correct_denominators_and_median(self):
        metric = aggregate_network(
            [
                self.station(1, 2, "OK", 50, ccs=2),
                self.station(2, 8, "TX", 150, ccs=8),
                self.station(3, 12, "DC", None, j3400=12),
            ]
        )

        self.assertEqual(metric["site_count"], 3)
        self.assertEqual(metric["dc_fast_port_count"], 22)
        self.assertEqual(metric["median_ports_per_site"], 8)
        self.assertEqual(metric["large_site_count"], 2)
        self.assertAlmostEqual(metric["large_site_percentage"], 66.666, places=2)
        self.assertEqual(metric["states_covered"], 3)
        self.assertEqual(metric["high_power_site_percentage"], 50)
        self.assertAlmostEqual(metric["power_data_coverage"], 66.666, places=2)

    def test_each_score_component_and_weight_total(self):
        validate_scoring_config()
        self.assertAlmostEqual(sum(SCORING_CONFIG["weights"].values()), 1.0)
        stations = [
            self.station(i, 12, "OK" if i < 5 else "TX", 350, ccs=6, j3400=6)
            for i in range(10)
        ]
        metric = aggregate_network(stations)
        score_networks([metric])

        self.assertTrue(metric["is_scored"])
        self.assertEqual(set(metric["score_components"]), set(SCORING_CONFIG["weights"]))
        self.assertEqual(metric["score_components"]["average_site_size"]["score"], 100)
        self.assertEqual(metric["score_components"]["large_site_share"]["score"], 100)
        self.assertEqual(metric["score_components"]["high_power_share"]["score"], 100)
        self.assertEqual(metric["score_components"]["connector_support"]["score"], 100)
        self.assertGreaterEqual(metric["infrastructure_score"], 0)
        self.assertLessEqual(metric["infrastructure_score"], 100)

    def test_grade_boundaries(self):
        expected = {
            90: "S", 89.9: "A", 80: "A", 79.9: "B", 70: "B",
            69.9: "C", 60: "C", 59.9: "D", 50: "D", 49.9: "F",
        }
        for score, grade in expected.items():
            with self.subTest(score=score):
                self.assertEqual(grade_for_score(score), grade)

    def test_network_config_has_stable_unique_keys_and_slugs(self):
        self.assertEqual(len(INCLUDED_NETWORKS), len(NETWORK_CONFIG_BY_KEY))
        self.assertEqual(
            len({network.slug for network in INCLUDED_NETWORKS}),
            len(INCLUDED_NETWORKS),
        )
        self.assertEqual(
            NETWORK_CONFIG_BY_KEY["RIVIAN_ADVENTURE"].slug,
            "rivian-adventure-network",
        )


class FakeNLRClient:
    def __init__(self, *, csv_text=None, catalog=None, error=None):
        self.csv_text = fixture_csv() if csv_text is None else csv_text
        self.catalog = catalog or [
            {
                "key": config.key,
                "name": config.display_name or config.key,
                "url": "https://example.com",
                "last_import_date": "2026-07-26",
                "import_type": "API",
            }
            for config in INCLUDED_NETWORKS
        ]
        self.error = error

    def fetch_network_catalog(self):
        if self.error:
            raise self.error
        return self.catalog

    def fetch_last_updated(self):
        return "2026-07-27T12:00:00Z"

    def fetch_charging_units_csv(self, network_keys=None):
        return self.csv_text


class ImportTests(TestCase):
    def test_successful_import_writes_and_activates_complete_snapshot(self):
        result = refresh_charging_networks(client=FakeNLRClient())

        self.assertEqual(result.status, ChargingDataImport.Status.SUCCEEDED)
        self.assertTrue(result.is_active)
        self.assertEqual(result.source_row_count, 11)
        self.assertEqual(result.normalized_station_count, 5)
        self.assertEqual(result.station_snapshots.count(), 5)
        self.assertEqual(result.network_metrics.count(), len(INCLUDED_NETWORKS))
        self.assertEqual(result.warnings["excluded_status_rows"], 2)

    def test_failed_fetch_retains_prior_snapshot(self):
        prior = refresh_charging_networks(client=FakeNLRClient())

        with self.assertRaises(RuntimeError):
            refresh_charging_networks(
                client=FakeNLRClient(error=RuntimeError("upstream unavailable"))
            )

        prior.refresh_from_db()
        self.assertTrue(prior.is_active)
        self.assertEqual(
            ChargingDataImport.objects.filter(
                status=ChargingDataImport.Status.FAILED
            ).count(),
            1,
        )

    def test_empty_source_is_rejected(self):
        with self.assertRaises(ChargingImportError):
            refresh_charging_networks(
                client=FakeNLRClient(csv_text="ID,EV Network\n")
            )
        self.assertFalse(ChargingDataImport.objects.filter(is_active=True).exists())

    def test_missing_configured_network_is_reported(self):
        catalog = FakeNLRClient().catalog
        catalog = [item for item in catalog if item["key"] != "WALMART"]

        result = refresh_charging_networks(
            client=FakeNLRClient(catalog=catalog)
        )

        self.assertIn(
            "WALMART",
            result.warnings["configured_networks_missing_from_catalog"],
        )

    def test_suspicious_site_decrease_is_rejected_without_override(self):
        prior = refresh_charging_networks(client=FakeNLRClient())
        rows = fixture_csv().splitlines()
        one_station_csv = "\n".join((rows[0], rows[5]))

        with self.assertRaises(ChargingImportError):
            refresh_charging_networks(
                client=FakeNLRClient(csv_text=one_station_csv)
            )

        prior.refresh_from_db()
        failed = ChargingDataImport.objects.filter(
            status=ChargingDataImport.Status.FAILED
        ).first()
        self.assertTrue(prior.is_active)
        self.assertEqual(failed.source_row_count, 1)
        self.assertIn("fell 80.0%", failed.error_message)


def create_active_snapshot():
    data_import = ChargingDataImport.objects.create(
        status=ChargingDataImport.Status.SUCCEEDED,
        started_at=timezone.now(),
        completed_at=timezone.now(),
        snapshot_date=date(2026, 7, 27),
        source_last_updated_at=timezone.now(),
        source_network_catalog_at=timezone.now(),
        source_row_count=20,
        normalized_station_count=20,
        included_network_count=2,
        schema_version="1.0",
        scoring_version="1.0",
        is_active=True,
    )
    return data_import


def create_metric(data_import, *, key, slug, name, score, ports, sites=10):
    network = ChargingNetwork.objects.create(
        network_key=key,
        slug=slug,
        name=name,
        network_url="https://example.com",
    )
    return ChargingNetworkMetricSnapshot.objects.create(
        data_import=data_import,
        snapshot_date=data_import.snapshot_date,
        network=network,
        site_count=sites,
        dc_fast_port_count=ports,
        average_ports_per_site=ports / sites,
        median_ports_per_site=ports / sites,
        small_site_count=0,
        large_site_count=sites,
        large_site_percentage=100,
        states_covered=2,
        state_coverage_percentage=2 / 51 * 100,
        state_counts={"OK": 6, "TX": 4},
        high_power_site_count=sites,
        high_power_site_percentage=100,
        ultra_high_power_site_count=sites,
        ultra_high_power_site_percentage=100,
        power_data_coverage=100,
        ccs_connector_count=ports,
        chademo_connector_count=0,
        j3400_connector_count=ports,
        mcs_connector_count=0,
        connector_types_supported=["CCS", "J3400/NACS"],
        site_size_distribution={"8-11": sites},
        power_distribution={"250-349": sites},
        is_scored=True,
        infrastructure_score=score,
        infrastructure_score_unrounded=score,
        infrastructure_grade=grade_for_score(score),
        score_components={
            key: {
                "raw": 100,
                "score": 100,
                "weight": weight,
                "weighted_contribution": 100 * weight,
            }
            for key, weight in SCORING_CONFIG["weights"].items()
        },
        source_network_last_import_date=date(2026, 7, 26),
    )


class PublicViewTests(TestCase):
    def setUp(self):
        self.data_import = create_active_snapshot()
        self.tesla = create_metric(
            self.data_import,
            key="Tesla",
            slug="tesla-supercharger",
            name="Tesla Supercharger",
            score=88.4,
            ports=120,
        )
        self.evgo = create_metric(
            self.data_import,
            key="eVgo Network",
            slug="evgo",
            name="EVgo",
            score=72.1,
            ports=180,
        )

    def test_leaderboard_renders_snapshot_and_score_disclaimer(self):
        response = self.client.get(reverse("evolve_site:charging_networks"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Charging Network Index")
        self.assertContains(response, "Tesla Supercharger")
        self.assertContains(response, "does not measure reliability")

    def test_leaderboard_sorts_by_port_count(self):
        response = self.client.get(
            reverse("evolve_site:charging_networks"),
            {"sort": "ports", "direction": "desc"},
        )
        content = response.content.decode()
        self.assertLess(content.index("EVgo"), content.index("Tesla Supercharger"))

    def test_detail_and_unknown_slug(self):
        response = self.client.get(
            reverse(
                "evolve_site:charging_network_detail",
                args=["tesla-supercharger"],
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Score breakdown")
        self.assertContains(response, "Connector mix")
        unknown = self.client.get(
            reverse("evolve_site:charging_network_detail", args=["unknown"])
        )
        self.assertEqual(unknown.status_code, 404)

    def test_methodology_renders_limitations(self):
        response = self.client.get(
            reverse("evolve_site:charging_network_methodology")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Methodology you can audit")
        self.assertContains(response, "It does not measure")

    def test_csv_export_has_expected_headers_and_values(self):
        response = self.client.get(reverse("evolve_site:charging_network_export"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn("snapshot_date,network_key,network_name", content)
        self.assertIn("Tesla,Tesla Supercharger", content)
        self.assertIn("source_network_last_import_date", content)
