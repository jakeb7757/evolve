from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("evolve_site", "0009_update_level1_voltage"),
    ]

    operations = [
        migrations.CreateModel(
            name="FuelEconomyVehicle",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("fueleconomy_id", models.PositiveIntegerField(unique=True)),
                ("model_year", models.PositiveIntegerField(db_index=True)),
                ("manufacturer", models.CharField(db_index=True, max_length=100)),
                ("model", models.CharField(max_length=255)),
                ("base_model", models.CharField(blank=True, max_length=255)),
                ("drivetrain", models.CharField(blank=True, max_length=100)),
                (
                    "epa_range_miles",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                (
                    "combined_kwh_per_100_miles",
                    models.DecimalField(
                        decimal_places=2,
                        help_text=(
                            "EPA combined electricity consumption in kWh per "
                            "100 miles"
                        ),
                        max_digits=6,
                    ),
                ),
                (
                    "charge_hours_120v",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=6, null=True
                    ),
                ),
                (
                    "charge_hours_240v",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=6, null=True
                    ),
                ),
                ("source_created_at", models.DateField(blank=True, null=True)),
                ("source_modified_at", models.DateField(blank=True, null=True)),
                ("last_synced_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
            ],
            options={
                "ordering": (
                    "-model_year",
                    "manufacturer",
                    "model",
                    "fueleconomy_id",
                ),
                "indexes": [
                    models.Index(
                        fields=["model_year", "manufacturer", "is_active"],
                        name="fev_year_make_active_idx",
                    )
                ],
            },
        ),
    ]
