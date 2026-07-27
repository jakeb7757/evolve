# Evolve

Evolve is a practical decision toolkit for drivers considering an electric
vehicle. It combines EPA vehicle data, personalized cost and charging
calculations, and nearby public fast-charging coverage in a responsive Django
application.

## Features

- **EV Fit Report** — Combine ownership savings, buffered EPA range, home
  charging, and an area snapshot of public 80+ kW stations into one shareable
  report.
- **Savings Calculator** — Compare the annual and five-year energy costs of a
  current gas vehicle with a specific EV.
- **Home Charging Calculator** — Determine whether a standard 120V outlet can
  replenish a typical day of driving or whether Level 2 charging is a better
  fit.
- **Fast-Charger Finder** — Search public stations rated at least 80 kW by ZIP
  code or city, then filter the complete result set by connector and the
  networks available in that area.
- **Charging Network Index** — Compare major U.S. public DC-fast networks using
  transparent, reproducible infrastructure metrics, network profiles, and a
  downloadable aggregate snapshot.
- **Community Status Reports** — Registered users can report a station as
  working, busy, or broken.
- **EPA Vehicle Catalog** — A scheduled synchronization keeps the local EV
  catalog current without making user requests depend on FuelEconomy.gov.

## Data sources

- [FuelEconomy.gov](https://www.fueleconomy.gov/) supplies EPA vehicle range,
  efficiency, and charging-time data.
- The [NLR Alternative Fuel Stations API](https://developer.nlr.gov/docs/transportation/alt-fuel-stations-v1/)
  supplies public charging locations, networks, connectors, port counts, and
  charging power.
- [OpenStreetMap Nominatim](https://nominatim.org/) geocodes ZIP codes and city
  searches for the station tools.

Estimates are planning guidance. Actual energy cost, vehicle efficiency, range,
charging speed, and station availability vary with conditions and provider
data.

## Technology

- Python 3.12 and Django 5.2
- PostgreSQL in production and SQLite for local development
- Google Cloud Run, Cloud SQL, Cloud Build, and Artifact Registry
- Bootstrap 5, Select2, and custom responsive CSS
- Gunicorn and WhiteNoise

## Local development

### 1. Clone and enter the repository

```bash
git clone <repository-url>
cd evolve
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows PowerShell, activate it with:

```powershell
.venv\Scripts\Activate.ps1
```

### 3. Configure local environment variables

Create a `.env` file beside `manage.py`:

```ini
SECRET_KEY=replace-with-a-local-development-key
NLR_API_KEY=replace-with-your-nlr-developer-key
```

The API key is required for station searches, the road-charging portion of the
EV Fit Report, and Charging Network Index refreshes. It is never exposed to
browser code. Existing deployments may temporarily keep the legacy
`NREL_API_KEY` variable; the settings layer accepts it as a fallback.

Do not set `DJANGO_SETTINGS_MODULE` for normal local development. `manage.py`
uses `evolve.settings.local`, which stores data in `db.sqlite3`.

### 4. Prepare the database

```bash
python manage.py migrate
python manage.py sync_fueleconomy --dry-run
python manage.py sync_fueleconomy
python manage.py refresh_charging_networks
```

The synchronization command downloads the official FuelEconomy.gov CSV and
keeps only battery-electric vehicles with valid combined energy-consumption
data.

### 5. Start the application

```bash
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

To access Django administration locally:

```bash
python manage.py createsuperuser
```

Then visit `http://127.0.0.1:8000/admin/`.

## Testing

Run the complete test suite:

```bash
python manage.py test
```

External API behavior is mocked in the tests, so the suite does not require
live NLR or FuelEconomy.gov requests.

Useful validation commands before a deployment:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

## Vehicle catalog synchronization

Validate the latest source without writing:

```bash
python manage.py sync_fueleconomy --dry-run
```

Apply the synchronization:

```bash
python manage.py sync_fueleconomy
```

The command validates the source schema and minimum record count before making
transactional inserts, updates, and stale-record deactivations.

Production job setup and scheduling are documented in
[docs/fueleconomy-cloud-run.md](docs/fueleconomy-cloud-run.md).

## Charging Network Index refresh

Refresh the precomputed NLR/AFDC snapshot and inspect its status:

```bash
python manage.py refresh_charging_networks
python manage.py charging_network_status
```

An import failure leaves the prior valid snapshot active. Production
architecture, scoring decisions, job bootstrap, daily scheduling, and the
large-decrease safety override are documented in
[docs/charging-network-index.md](docs/charging-network-index.md).

## Deployment

Production is deployed to Google Cloud Run through the repository’s Cloud Build
trigger. A push to the configured `master` branch runs `cloudbuild.yaml`, which:

1. Builds and pushes an immutable container image to Artifact Registry.
2. Updates and executes the Cloud Run migration job.
3. Updates the scheduled vehicle-catalog and Charging Network Index jobs.
4. Deploys the new application revision.
5. Routes service traffic to the latest ready revision.

The Cloud Run service and jobs retain their existing Cloud SQL connection,
secrets, and environment configuration when the pipeline updates their image.

The production environment variables are documented in `.env.example`. Never
commit a populated `.env` file or credential values.

## Project structure

```text
evolve/
├── evolve/                 Django project settings and root URLs
├── evolve_site/            Application models, views, forms, services, and UI
│   ├── charging_index/     NLR parsing, aggregation, scoring, and imports
│   ├── management/         Vehicle and charging-data refresh commands
│   ├── migrations/         Database schema history
│   ├── static/             CSS, JavaScript, and city suggestion data
│   └── templates/          Django templates
├── docs/                   Production operations documentation
├── scripts/                Cloud Run bootstrap and maintenance scripts
├── cloudbuild.yaml         Build, migration, and deployment pipeline
├── Dockerfile              Cloud Run application image
├── manage.py               Django command entry point
└── requirements.txt        Python dependencies
```
