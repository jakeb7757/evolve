from django.core.management.base import BaseCommand, CommandError

from evolve_site.charging_index.importer import refresh_charging_networks


class Command(BaseCommand):
    help = "Refresh and atomically activate the NLR Charging Network Index snapshot."

    def add_arguments(self, parser):
        parser.add_argument(
            "--allow-large-decrease",
            action="store_true",
            help="Activate a snapshot after a verified site-count decrease over 25%%.",
        )

    def handle(self, *args, **options):
        try:
            data_import = refresh_charging_networks(
                allow_large_decrease=options["allow_large_decrease"]
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                "Activated charging snapshot "
                f"{data_import.snapshot_date}: "
                f"{data_import.normalized_station_count:,} stations across "
                f"{data_import.included_network_count} included networks."
            )
        )
