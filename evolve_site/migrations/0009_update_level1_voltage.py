from django.db import migrations, models


def update_level1_voltage(apps, schema_editor):
    submission = apps.get_model('evolve_site', 'Level2CalculatorSubmission')
    submission.objects.filter(home_voltage='110').update(home_voltage='120')


def restore_level1_voltage(apps, schema_editor):
    submission = apps.get_model('evolve_site', 'Level2CalculatorSubmission')
    submission.objects.filter(home_voltage='120').update(home_voltage='110')


class Migration(migrations.Migration):

    dependencies = [
        ('evolve_site', '0008_stationstatus'),
    ]

    operations = [
        migrations.RunPython(update_level1_voltage, restore_level1_voltage),
        migrations.AlterField(
            model_name='level2calculatorsubmission',
            name='home_voltage',
            field=models.CharField(
                choices=[('120', '120V'), ('240', '240V')],
                max_length=10,
            ),
        ),
    ]
