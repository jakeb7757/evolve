from django.contrib import admin
from .models import ElectricVehicle, FuelEconomyVehicle, Level2CalculatorSubmission

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
