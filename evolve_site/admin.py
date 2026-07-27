from django.contrib import admin
from .models import (
    ChargingDataImport,
    ChargingNetwork,
    ChargingNetworkMetricSnapshot,
    ElectricVehicle,
    FuelEconomyVehicle,
    Level2CalculatorSubmission,
)

@admin.register(ElectricVehicle)
class ElectricVehicleAdmin(admin.ModelAdmin):
    """
    Admin view for ElectricVehicle model.
    """
    list_display = ('manufacturer', 'model', 'model_year', 'epa_range_miles', 'battery_capacity_kwh')
    search_fields = ('manufacturer', 'model')
    list_filter = ('model_year', 'manufacturer')


@admin.register(FuelEconomyVehicle)
class FuelEconomyVehicleAdmin(admin.ModelAdmin):
    list_display = (
        "manufacturer",
        "model",
        "model_year",
        "epa_range_miles",
        "combined_kwh_per_100_miles",
        "is_active",
        "last_synced_at",
    )
    search_fields = ("manufacturer", "model", "fueleconomy_id")
    list_filter = ("is_active", "model_year", "manufacturer")
    readonly_fields = ("last_synced_at",)


@admin.register(Level2CalculatorSubmission)
class Level2CalculatorSubmissionAdmin(admin.ModelAdmin):
    list_display = ('user', 'ev_model', 'daily_miles', 'charging_hours', 'home_voltage', 'recommendation', 'submitted_at')
    search_fields = ('ev_model', 'user__username', 'recommendation')
    list_filter = ('home_voltage', 'recommendation', 'submitted_at')


@admin.register(ChargingDataImport)
class ChargingDataImportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "status",
        "snapshot_date",
        "normalized_station_count",
        "included_network_count",
        "is_active",
        "completed_at",
    )
    list_filter = ("status", "is_active", "schema_version", "scoring_version")
    readonly_fields = (
        "started_at",
        "completed_at",
        "source_last_updated_at",
        "source_network_catalog_at",
        "source_row_count",
        "normalized_station_count",
        "included_network_count",
        "error_message",
        "warnings",
    )


@admin.register(ChargingNetwork)
class ChargingNetworkAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "network_key",
        "is_active",
        "is_included",
        "source_last_import_date",
    )
    search_fields = ("name", "network_key")
    list_filter = ("is_active", "is_included", "import_type")


@admin.register(ChargingNetworkMetricSnapshot)
class ChargingNetworkMetricSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "network",
        "snapshot_date",
        "site_count",
        "dc_fast_port_count",
        "infrastructure_score",
        "is_scored",
    )
    list_filter = ("snapshot_date", "is_scored", "infrastructure_grade")
