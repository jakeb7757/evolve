from django.db import models
from django.contrib.auth import get_user_model


class ElectricVehicle(models.Model):
    """
    Represents an electric vehicle with its specifications, mapped to an existing table.
    """
    manufacturer = models.CharField(max_length=255, default='')
    model = models.CharField(max_length=255, default='')
    model_year = models.IntegerField(default=2024)
    battery_capacity_kwh = models.DecimalField(
        max_digits=5, decimal_places=1, help_text="Battery capacity in kWh"
    )
    epa_range_miles = models.PositiveIntegerField(
        help_text="EPA estimated range in miles", db_column='electric_range_miles'
    )
    # The charge_speed_l1_mph column is ignored for now as it's not needed.

    class Meta:
        db_table = 'vehicles'
        managed = False # Tell Django to use the existing table

    def __str__(self) -> str:
        """Returns the string representation of the EV."""
        return f"{self.model_year} {self.manufacturer} {self.model}"

    @property
    def efficiency_wh_per_mile(self) -> float:
        """Calculates efficiency in Watt-hours per mile."""
        if self.epa_range_miles > 0:
            return float((self.battery_capacity_kwh * 1000) / self.epa_range_miles)
        return 0.0


class FuelEconomyVehicle(models.Model):
    """An EPA FuelEconomy.gov vehicle record used by Evolve's calculators."""

    fueleconomy_id = models.PositiveIntegerField(unique=True)
    model_year = models.PositiveIntegerField(db_index=True)
    manufacturer = models.CharField(max_length=100, db_index=True)
    model = models.CharField(max_length=255)
    base_model = models.CharField(max_length=255, blank=True)
    drivetrain = models.CharField(max_length=100, blank=True)
    epa_range_miles = models.PositiveIntegerField(null=True, blank=True)
    combined_kwh_per_100_miles = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        help_text="EPA combined electricity consumption in kWh per 100 miles",
    )
    charge_hours_120v = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    charge_hours_240v = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    source_created_at = models.DateField(null=True, blank=True)
    source_modified_at = models.DateField(null=True, blank=True)
    last_synced_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ("-model_year", "manufacturer", "model", "fueleconomy_id")
        indexes = [
            models.Index(
                fields=("model_year", "manufacturer", "is_active"),
                name="fev_year_make_active_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.model_year} {self.manufacturer} {self.model}"

    @property
    def efficiency_wh_per_mile(self) -> float:
        """Convert EPA kWh/100 miles to Wh/mile."""
        return float(self.combined_kwh_per_100_miles * 10)

    @property
    def option_label(self) -> str:
        """A useful dropdown label for otherwise similar EPA records."""
        if self.drivetrain and self.drivetrain.lower() not in self.model.lower():
            return f"{self.model} ({self.drivetrain})"
        return self.model


class Level2CalculatorSubmission(models.Model):
    user = models.ForeignKey(get_user_model(), on_delete=models.SET_NULL, null=True, blank=True)
    ev_model = models.CharField(max_length=100)
    battery_capacity_kwh = models.DecimalField(max_digits=6, decimal_places=2)
    daily_miles = models.PositiveIntegerField()
    charging_hours = models.PositiveIntegerField()
    home_voltage = models.CharField(max_length=10, choices=[('120', '120V'), ('240', '240V')])
    recommendation = models.CharField(max_length=255)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Level 2 Calculator Submission"
        verbose_name_plural = "Level 2 Calculator Submissions"

    def __str__(self):
        return f"{self.ev_model} ({self.daily_miles} mi/day) - {self.recommendation}"

class StationStatus(models.Model):
    STATUS_CHOICES = [
        ('Working', 'Working'),
        ('Broken', 'Broken'),
        ('Busy', 'Busy'),
    ]
    nrel_station_id = models.CharField(max_length=255)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES)
    user = models.ForeignKey(get_user_model(), on_delete=models.SET_NULL, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Station {self.nrel_station_id}: {self.status}"
