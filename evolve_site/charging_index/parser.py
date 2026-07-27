import csv
import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from .config import NETWORK_CONFIG_BY_KEY


NUMBER_PATTERN = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")


@dataclass
class DataQualityReport:
    source_rows: int = 0
    missing_station_id_rows: int = 0
    unknown_network_key_rows: int = 0
    excluded_network_rows: int = 0
    conflicting_network_stations: int = 0
    excluded_status_rows: int = 0
    non_public_access_rows: int = 0
    zero_or_missing_port_stations: int = 0
    missing_state_stations: int = 0
    missing_power_stations: int = 0
    configured_networks_missing_from_catalog: list[str] = field(default_factory=list)
    unknown_network_keys: set[str] = field(default_factory=set)

    def as_dict(self) -> dict:
        return {
            "source_rows": self.source_rows,
            "missing_station_id_rows": self.missing_station_id_rows,
            "unknown_network_key_rows": self.unknown_network_key_rows,
            "excluded_network_rows": self.excluded_network_rows,
            "conflicting_network_stations": self.conflicting_network_stations,
            "excluded_status_rows": self.excluded_status_rows,
            "non_public_access_rows": self.non_public_access_rows,
            "zero_or_missing_port_stations": self.zero_or_missing_port_stations,
            "missing_state_stations": self.missing_state_stations,
            "missing_power_stations": self.missing_power_stations,
            "configured_networks_missing_from_catalog": sorted(
                self.configured_networks_missing_from_catalog
            ),
            "unknown_network_keys": sorted(self.unknown_network_keys),
        }


@dataclass
class StationRecord:
    station_id: str
    network_key: str
    station_name: str | None = None
    street_address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    status_code: str | None = None
    access_code: str | None = None
    facility_type: str | None = None
    dc_fast_port_count: int = 0
    ccs_connector_count: int = 0
    chademo_connector_count: int = 0
    j3400_connector_count: int = 0
    mcs_connector_count: int = 0
    ccs_power_kw_values: list[float] = field(default_factory=list)
    chademo_power_kw_values: list[float] = field(default_factory=list)
    j3400_power_kw_values: list[float] = field(default_factory=list)
    mcs_power_kw_values: list[float] = field(default_factory=list)
    max_power_kw: float | None = None


ALIASES = {
    "station_id": ("ID", "id", "Station ID", "station_id"),
    "network_key": ("EV Network", "EV Network Key", "ev_network", "network_key"),
    "station_name": ("Station Name", "station_name"),
    "street_address": ("Street Address", "street_address"),
    "city": ("City", "city"),
    "state": ("State", "state"),
    "zip_code": ("ZIP", "ZIP Code", "zip"),
    "latitude": ("Latitude", "latitude"),
    "longitude": ("Longitude", "longitude"),
    "status_code": ("Status Code", "status_code"),
    "access_code": ("Access Code", "access_code"),
    "facility_type": ("Facility Type", "facility_type"),
    "dc_fast_port_count": ("EV DC Fast Count", "ev_dc_fast_num"),
    "ccs_connector_count": ("EV CCS Connector Count",),
    "chademo_connector_count": ("EV CHAdeMO Connector Count",),
    "j3400_connector_count": ("EV J3400 Connector Count",),
    "mcs_connector_count": ("EV J3271 Connector Count",),
    "ccs_power": ("EV CCS Power Output (kW)",),
    "chademo_power": ("EV CHAdeMO Power Output (kW)",),
    "j3400_power": ("EV J3400 Power Output (kW)",),
    "mcs_power": ("EV J3271 Power Output (kW)",),
}


def clean_text(value) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def row_value(row: dict, field_name: str):
    for key in ALIASES[field_name]:
        value = clean_text(row.get(key))
        if value is not None:
            return value
    return None


def parse_int(value) -> int | None:
    value = clean_text(value)
    if value is None:
        return None
    try:
        parsed = int(Decimal(value.replace(",", "")))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed >= 0 else None


def parse_decimal(value) -> Decimal | None:
    value = clean_text(value)
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def parse_power_values(value) -> list[float]:
    value = clean_text(value)
    if value is None:
        return []
    parsed = []
    for match in NUMBER_PATTERN.findall(value.replace(",", " ")):
        try:
            number = float(match)
        except ValueError:
            continue
        if number >= 0 and number not in parsed:
            parsed.append(number)
    return sorted(parsed)


def _first_nonempty(rows: list[dict], field_name: str):
    for row in rows:
        value = row_value(row, field_name)
        if value is not None:
            return value
    return None


def _connector_count(rows: list[dict], count_field: str) -> int:
    """Connector counts are station totals and repeat across charging-unit rows."""
    counts = [
        count
        for row in rows
        if (count := parse_int(row_value(row, count_field))) is not None
    ]
    return max(counts, default=0)


def _power_values(rows: list[dict], field_name: str) -> list[float]:
    values = set()
    for row in rows:
        values.update(parse_power_values(row_value(row, field_name)))
    return sorted(values)


def parse_station_csv(
    csv_content: str | bytes | io.TextIOBase,
    *,
    allowed_network_keys: set[str] | None = None,
    known_network_keys: set[str] | None = None,
) -> tuple[list[StationRecord], DataQualityReport]:
    if isinstance(csv_content, bytes):
        stream = io.StringIO(csv_content.decode("utf-8-sig"))
    elif isinstance(csv_content, str):
        stream = io.StringIO(csv_content.lstrip("\ufeff"))
    else:
        stream = csv_content

    allowed = allowed_network_keys or set(NETWORK_CONFIG_BY_KEY)
    known = known_network_keys or allowed
    report = DataQualityReport()
    grouped: dict[str, list[dict]] = {}

    for row in csv.DictReader(stream):
        report.source_rows += 1
        station_id = row_value(row, "station_id")
        network_key = row_value(row, "network_key")
        if station_id is None:
            report.missing_station_id_rows += 1
            continue
        if network_key is None or network_key not in known:
            report.unknown_network_key_rows += 1
            if network_key:
                report.unknown_network_keys.add(network_key)
            continue
        if network_key not in allowed:
            report.excluded_network_rows += 1
            continue
        status_code = (row_value(row, "status_code") or "").upper()
        if status_code in {"P", "T"}:
            report.excluded_status_rows += 1
            continue
        access_code = (row_value(row, "access_code") or "").lower()
        if access_code and access_code != "public":
            report.non_public_access_rows += 1
            continue
        grouped.setdefault(station_id, []).append(row)

    stations = []
    for station_id, rows in grouped.items():
        row_network_keys = {
            row_value(row, "network_key") for row in rows if row_value(row, "network_key")
        }
        if len(row_network_keys) > 1:
            report.conflicting_network_stations += 1
        network_key = row_value(rows[0], "network_key")
        port_values = [
            value
            for row in rows
            if (value := parse_int(row_value(row, "dc_fast_port_count"))) is not None
        ]
        power_fields = ("ccs_power", "chademo_power", "j3400_power", "mcs_power")
        power_lists = {field: _power_values(rows, field) for field in power_fields}
        all_power = [value for values in power_lists.values() for value in values]
        state = clean_text(_first_nonempty(rows, "state"))
        station = StationRecord(
            station_id=station_id,
            network_key=network_key,
            station_name=_first_nonempty(rows, "station_name"),
            street_address=_first_nonempty(rows, "street_address"),
            city=_first_nonempty(rows, "city"),
            state=state.upper() if state else None,
            zip_code=_first_nonempty(rows, "zip_code"),
            latitude=parse_decimal(_first_nonempty(rows, "latitude")),
            longitude=parse_decimal(_first_nonempty(rows, "longitude")),
            status_code=_first_nonempty(rows, "status_code"),
            access_code=_first_nonempty(rows, "access_code"),
            facility_type=_first_nonempty(rows, "facility_type"),
            # This value is station-level and repeats on every unit row.
            dc_fast_port_count=max(port_values, default=0),
            ccs_connector_count=_connector_count(rows, "ccs_connector_count"),
            chademo_connector_count=_connector_count(
                rows, "chademo_connector_count"
            ),
            j3400_connector_count=_connector_count(rows, "j3400_connector_count"),
            mcs_connector_count=_connector_count(rows, "mcs_connector_count"),
            ccs_power_kw_values=power_lists["ccs_power"],
            chademo_power_kw_values=power_lists["chademo_power"],
            j3400_power_kw_values=power_lists["j3400_power"],
            mcs_power_kw_values=power_lists["mcs_power"],
            max_power_kw=max(all_power) if all_power else None,
        )
        if station.dc_fast_port_count == 0:
            report.zero_or_missing_port_stations += 1
        if station.state is None:
            report.missing_state_stations += 1
        if station.max_power_kw is None:
            report.missing_power_stations += 1
        stations.append(station)

    return stations, report
