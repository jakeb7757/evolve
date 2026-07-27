import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from evolve_site.models import FuelEconomyVehicle


DEFAULT_SOURCE_URL = "https://www.fueleconomy.gov/feg/epadata/vehicles.csv"
REQUIRED_COLUMNS = {
    "id",
    "year",
    "make",
    "model",
    "atvType",
    "fuelType1",
    "combE",
}
SYNC_FIELDS = (
    "model_year",
    "manufacturer",
    "model",
    "base_model",
    "drivetrain",
    "epa_range_miles",
    "combined_kwh_per_100_miles",
    "charge_hours_120v",
    "charge_hours_240v",
    "source_created_at",
    "source_modified_at",
    "is_active",
)


def optional_decimal(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    return number.quantize(Decimal("0.01")) if number >= 0 else None


def optional_positive_integer(value):
    number = optional_decimal(value)
    if number is None or number <= 0:
        return None
    return int(number)


def optional_date(value):
    value = (value or "").strip()
    if not value:
        return None

    for date_format in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            pass

    # FuelEconomy.gov CSV dates commonly look like:
    # "Tue Jan 01 00:00:00 EST 2013".
    parts = value.split()
    if len(parts) >= 4:
        shortened = " ".join((parts[0], parts[1], parts[2], parts[-1]))
        try:
            return datetime.strptime(shortened, "%a %b %d %Y").date()
        except ValueError:
            pass
    return None


def is_battery_electric(row):
    return (
        (row.get("atvType") or "").strip().upper() == "EV"
        or (row.get("fuelType1") or "").strip().lower() == "electricity"
    )


def parse_vehicle_rows(stream):
    reader = csv.DictReader(stream)
    fieldnames = set(reader.fieldnames or [])
    missing_columns = sorted(REQUIRED_COLUMNS - fieldnames)
    if missing_columns:
        raise CommandError(
            "FuelEconomy.gov CSV is missing required columns: "
            + ", ".join(missing_columns)
        )

    vehicles = {}
    rejected = 0
    for row in reader:
        if not is_battery_electric(row):
            continue

        try:
            source_id = int((row.get("id") or "").strip())
            model_year = int((row.get("year") or "").strip())
            manufacturer = (row.get("make") or "").strip()
            model = (row.get("model") or "").strip()
            combined_efficiency = optional_decimal(row.get("combE"))
        except (TypeError, ValueError):
            rejected += 1
            continue

        if (
            source_id <= 0
            or model_year <= 0
            or not manufacturer
            or not model
            or combined_efficiency is None
            or combined_efficiency <= 0
        ):
            rejected += 1
            continue

        vehicles[source_id] = {
            "model_year": model_year,
            "manufacturer": manufacturer,
            "model": model,
            "base_model": (row.get("baseModel") or row.get("basemodel") or "").strip(),
            "drivetrain": (row.get("drive") or "").strip(),
            "epa_range_miles": optional_positive_integer(row.get("range")),
            "combined_kwh_per_100_miles": combined_efficiency,
            "charge_hours_120v": optional_decimal(row.get("charge120")),
            "charge_hours_240v": optional_decimal(row.get("charge240")),
            "source_created_at": optional_date(row.get("createdOn")),
            "source_modified_at": optional_date(row.get("modifiedOn")),
            "is_active": True,
        }
    return vehicles, rejected


class Command(BaseCommand):
    help = "Synchronize battery-electric vehicles from FuelEconomy.gov."

    def add_arguments(self, parser):
        parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
        parser.add_argument(
            "--file",
            type=Path,
            help="Read a local CSV instead of downloading the official dataset.",
        )
        parser.add_argument(
            "--minimum-records",
            type=int,
            default=100,
            help="Abort before writing if fewer valid EV records are found.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and compare the dataset without changing the database.",
        )

    def handle(self, *args, **options):
        stream = self._open_stream(options)
        try:
            vehicles, rejected = parse_vehicle_rows(stream)
        finally:
            stream.close()

        minimum_records = options["minimum_records"]
        if len(vehicles) < minimum_records:
            raise CommandError(
                f"Import contained {len(vehicles)} valid EV records; "
                f"minimum is {minimum_records}. No database changes were made."
            )

        source_ids = set(vehicles)
        existing = {
            vehicle.fueleconomy_id: vehicle
            for vehicle in FuelEconomyVehicle.objects.filter(
                fueleconomy_id__in=source_ids
            )
        }
        new_ids = source_ids - set(existing)
        changed_ids = set()
        for source_id, vehicle in existing.items():
            values = vehicles[source_id]
            if any(
                getattr(vehicle, field) != values[field]
                for field in SYNC_FIELDS
            ):
                changed_ids.add(source_id)
        unchanged_count = len(existing) - len(changed_ids)
        stale_count = (
            FuelEconomyVehicle.objects.filter(is_active=True)
            .exclude(fueleconomy_id__in=source_ids)
            .count()
        )

        summary = (
            f"{len(new_ids)} new, {len(changed_ids)} updated, "
            f"{unchanged_count} unchanged, {stale_count} deactivated, "
            f"{rejected} rejected"
        )
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(f"Dry run: {summary}"))
            return

        synced_at = timezone.now()
        new_objects = [
            FuelEconomyVehicle(
                fueleconomy_id=source_id,
                last_synced_at=synced_at,
                **vehicles[source_id],
            )
            for source_id in new_ids
        ]
        changed_objects = []
        for source_id in changed_ids:
            vehicle = existing[source_id]
            for field, value in vehicles[source_id].items():
                setattr(vehicle, field, value)
            vehicle.last_synced_at = synced_at
            changed_objects.append(vehicle)

        with transaction.atomic():
            FuelEconomyVehicle.objects.bulk_create(new_objects, batch_size=500)
            if changed_objects:
                FuelEconomyVehicle.objects.bulk_update(
                    changed_objects,
                    fields=(*SYNC_FIELDS, "last_synced_at"),
                    batch_size=500,
                )
            (
                FuelEconomyVehicle.objects.filter(is_active=True)
                .exclude(fueleconomy_id__in=source_ids)
                .update(is_active=False, last_synced_at=synced_at)
            )
            FuelEconomyVehicle.objects.filter(
                fueleconomy_id__in=source_ids
            ).update(last_synced_at=synced_at)

        self.stdout.write(self.style.SUCCESS(f"FuelEconomy.gov sync complete: {summary}"))

    def _open_stream(self, options):
        local_file = options["file"]
        if local_file:
            try:
                return local_file.open(encoding="utf-8-sig", newline="")
            except OSError as exc:
                raise CommandError(f"Could not read {local_file}: {exc}") from exc

        try:
            response = requests.get(
                options["source_url"],
                headers={"User-Agent": "Evolve EV catalog sync"},
                timeout=(10, 120),
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise CommandError(f"FuelEconomy.gov download failed: {exc}") from exc

        try:
            content = response.content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise CommandError("FuelEconomy.gov CSV was not valid UTF-8.") from exc
        return io.StringIO(content, newline="")
