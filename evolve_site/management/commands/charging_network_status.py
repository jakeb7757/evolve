from django.core.management.base import BaseCommand

from evolve_site.models import ChargingDataImport


class Command(BaseCommand):
    help = "Show Charging Network Index import status without exposing credentials."

    def handle(self, *args, **options):
        successful = ChargingDataImport.objects.filter(
            status=ChargingDataImport.Status.SUCCEEDED
        ).first()
        failed = ChargingDataImport.objects.filter(
            status=ChargingDataImport.Status.FAILED
        ).first()
        active = ChargingDataImport.objects.filter(is_active=True).first()

        self.stdout.write(f"Active snapshot: {active.snapshot_date if active else 'none'}")
        if successful:
            self.stdout.write(f"Last successful import: {successful.completed_at}")
            self.stdout.write(
                f"NLR dataset last updated: {successful.source_last_updated_at}"
            )
            self.stdout.write(f"Source rows: {successful.source_row_count:,}")
            self.stdout.write(
                f"Normalized stations: {successful.normalized_station_count:,}"
            )
            self.stdout.write(
                f"Included networks with stations: {successful.included_network_count}"
            )
            self.stdout.write(
                f"Schema/scoring versions: "
                f"{successful.schema_version}/{successful.scoring_version}"
            )
            warnings = successful.warnings or {}
            self.stdout.write(
                f"Warnings: missing station IDs={warnings.get('missing_station_id_rows', 0)}, "
                f"unknown networks={warnings.get('unknown_network_key_rows', 0)}, "
                f"missing power={warnings.get('missing_power_stations', 0)}"
            )
        if failed:
            self.stdout.write(f"Last failed import: {failed.completed_at}")
            self.stdout.write(f"Failure: {failed.error_message}")
