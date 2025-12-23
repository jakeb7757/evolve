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

class Level2CalculatorSubmission(models.Model):
    user = models.ForeignKey(get_user_model(), on_delete=models.SET_NULL, null=True, blank=True)
    ev_model = models.CharField(max_length=100)
    battery_capacity_kwh = models.DecimalField(max_digits=6, decimal_places=2)
    daily_miles = models.PositiveIntegerField()
    charging_hours = models.PositiveIntegerField()
    home_voltage = models.CharField(max_length=10, choices=[('110', '110V'), ('240', '240V')])
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
