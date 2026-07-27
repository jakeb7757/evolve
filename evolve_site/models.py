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


class ChargingDataImport(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    status = models.CharField(max_length=16, choices=Status.choices)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    snapshot_date = models.DateField(null=True, blank=True)
    source_last_updated_at = models.DateTimeField(null=True, blank=True)
    source_network_catalog_at = models.DateTimeField(null=True, blank=True)
    source_row_count = models.PositiveIntegerField(default=0)
    normalized_station_count = models.PositiveIntegerField(default=0)
    included_network_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    warnings = models.JSONField(default=dict, blank=True)
    schema_version = models.CharField(max_length=20)
    scoring_version = models.CharField(max_length=20)
    is_active = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ("-started_at",)

    def __str__(self):
        return f"Charging import {self.pk} ({self.status})"


class ChargingNetwork(models.Model):
    network_key = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    name = models.CharField(max_length=255)
    short_name = models.CharField(max_length=100, blank=True)
    network_url = models.URLField(blank=True)
    import_type = models.CharField(max_length=30, blank=True)
    source_last_import_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_included = models.BooleanField(default=True)
    include_in_leaderboard = models.BooleanField(default=True)
    minimum_site_count = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class ChargingStationSnapshot(models.Model):
    data_import = models.ForeignKey(
        ChargingDataImport, on_delete=models.CASCADE, related_name="station_snapshots"
    )
    snapshot_date = models.DateField(db_index=True)
    station_id = models.CharField(max_length=100)
    network = models.ForeignKey(
        ChargingNetwork, on_delete=models.CASCADE, related_name="station_snapshots"
    )
    station_name = models.CharField(max_length=255, blank=True)
    street_address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=8, blank=True, db_index=True)
    zip = models.CharField(max_length=12, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    status_code = models.CharField(max_length=4, blank=True)
    access_code = models.CharField(max_length=20, blank=True)
    facility_type = models.CharField(max_length=80, blank=True)
    dc_fast_port_count = models.PositiveIntegerField(default=0)
    ccs_connector_count = models.PositiveIntegerField(default=0)
    chademo_connector_count = models.PositiveIntegerField(default=0)
    j3400_connector_count = models.PositiveIntegerField(default=0)
    mcs_connector_count = models.PositiveIntegerField(default=0)
    ccs_power_kw_values = models.JSONField(default=list)
    chademo_power_kw_values = models.JSONField(default=list)
    j3400_power_kw_values = models.JSONField(default=list)
    mcs_power_kw_values = models.JSONField(default=list)
    max_power_kw = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("data_import", "network", "station_id"),
                name="charging_station_snapshot_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=("data_import", "network"),
                name="charge_station_import_net_idx",
            )
        ]


class ChargingNetworkMetricSnapshot(models.Model):
    data_import = models.ForeignKey(
        ChargingDataImport, on_delete=models.CASCADE, related_name="network_metrics"
    )
    snapshot_date = models.DateField(db_index=True)
    network = models.ForeignKey(
        ChargingNetwork, on_delete=models.CASCADE, related_name="metric_snapshots"
    )
    site_count = models.PositiveIntegerField()
    dc_fast_port_count = models.PositiveIntegerField()
    average_ports_per_site = models.DecimalField(max_digits=8, decimal_places=3)
    median_ports_per_site = models.DecimalField(max_digits=8, decimal_places=3)
    small_site_count = models.PositiveIntegerField()
    large_site_count = models.PositiveIntegerField()
    large_site_percentage = models.DecimalField(max_digits=6, decimal_places=3)
    states_covered = models.PositiveSmallIntegerField()
    state_coverage_percentage = models.DecimalField(max_digits=6, decimal_places=3)
    territories_covered = models.JSONField(default=list)
    state_counts = models.JSONField(default=dict)
    high_power_site_count = models.PositiveIntegerField()
    high_power_site_percentage = models.DecimalField(
        max_digits=6, decimal_places=3, null=True, blank=True
    )
    ultra_high_power_site_count = models.PositiveIntegerField()
    ultra_high_power_site_percentage = models.DecimalField(
        max_digits=6, decimal_places=3, null=True, blank=True
    )
    power_data_coverage = models.DecimalField(max_digits=6, decimal_places=3)
    ccs_connector_count = models.PositiveIntegerField()
    chademo_connector_count = models.PositiveIntegerField()
    j3400_connector_count = models.PositiveIntegerField()
    mcs_connector_count = models.PositiveIntegerField()
    connector_types_supported = models.JSONField(default=list)
    site_size_distribution = models.JSONField(default=dict)
    power_distribution = models.JSONField(default=dict)
    is_scored = models.BooleanField(default=True)
    infrastructure_score = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True
    )
    infrastructure_score_unrounded = models.DecimalField(
        max_digits=10, decimal_places=6, null=True, blank=True
    )
    infrastructure_grade = models.CharField(max_length=1, blank=True)
    score_components = models.JSONField(default=dict)
    source_network_last_import_date = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("data_import", "network"),
                name="charging_network_metric_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=("data_import", "-infrastructure_score"),
                name="charge_metric_import_score_idx",
            )
        ]
        ordering = ("-infrastructure_score", "network__name")
