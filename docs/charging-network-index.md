# Charging Network Index architecture and operations

## Detected application stack

This implementation follows Evolve's existing architecture:

- Django 5.2 on Python 3.12 with standard Django URL routing and templates
- Django ORM with PostgreSQL/Cloud SQL in production and SQLite locally
- Bootstrap 5 plus the existing custom responsive stylesheet
- Google Cloud Build, Cloud Run, Cloud Run Jobs, and Cloud Scheduler
- Django `TestCase` and `unittest.mock`
- Local-memory Django caching and no existing chart or mapping dependency

The index therefore uses relational historical snapshots in the existing
database, a Django management command for imports, and semantic HTML/CSS charts
with data tables. It does not introduce a second service, JavaScript framework,
database, or charting package. User-facing requests read the active precomputed
snapshot and never call NLR.

## Data and scoring architecture

The import uses three official NLR endpoints:

- `GET /api/alt-fuel-stations/v1/electric-networks.json`
- `GET /api/alt-fuel-stations/v1/ev-charging-units.csv`
- `GET /api/alt-fuel-stations/v1/last-updated.json`

The API key is sent in the `X-Api-Key` header and is never placed in a logged
URL. The charging-unit request is filtered to U.S., public, available DC-fast
stations. A configured allowlist is validated against the network catalog on
each import; a missing key becomes a visible warning.

Charging-unit rows are grouped by NLR station ID within each network. Repeated
station-level port and connector totals are counted once using their maximum
reported station value, unique power values are retained, and missing power
remains null. Rivian Adventure Network and Rivian Waypoints are not combined.

The models retain historical imports, station snapshots, and aggregate network
snapshots. A candidate dataset is parsed, aggregated, scored, and validated
before it is written. Snapshot creation and active-snapshot switching happen in
one database transaction. A failed import is recorded but never deactivates the
prior valid snapshot.

Scoring constants live in `evolve_site/charging_index/config.py` and have an
independent scoring version. The public methodology page exposes every raw
metric, normalized component, weight, and contribution.

## Local operation

Set the server-only key in `.env`:

```ini
NLR_API_KEY=replace-with-your-nlr-key
```

Apply migrations and refresh:

```bash
python manage.py migrate
python manage.py refresh_charging_networks
python manage.py charging_network_status
```

Use the guarded override only after checking the source when a legitimate
snapshot shrinks by more than 25 percent:

```bash
python manage.py refresh_charging_networks --allow-large-decrease
```

Public routes:

- `/charging-networks/`
- `/charging-networks/<network-slug>/`
- `/charging-networks/methodology/`
- `/charging-networks/export.csv`
- `/charging-networks/embed/leaderboard/`

## Production setup

The production service must have `NLR_API_KEY`. Existing deployments that
currently expose only `NREL_API_KEY` remain compatible, but `NLR_API_KEY` is the
preferred name.

After the first deployment containing the new command, create the refresh job.
The script reads the current immutable image from `evolve-app` automatically:

```bash
bash scripts/bootstrap-cloud-run-jobs.sh
```

Then create or update the daily schedule (3:20 a.m. Central by default):

```bash
bash scripts/bootstrap-charging-scheduler.sh
```

The scheduler script grants its existing service account permission to invoke
this job and then creates or updates the authenticated Scheduler request.

Run and inspect the first import:

```bash
gcloud run jobs execute evolve-refresh-charging \
  --project portfolio-478704 \
  --region us-central1 \
  --wait

gcloud run jobs executions list \
  --job evolve-refresh-charging \
  --project portfolio-478704 \
  --region us-central1
```

Cloud Build conditionally updates the refresh job to each immutable application
image after the job has been bootstrapped. The first build safely skips that
step when the job does not exist.

## Public limitations

The Infrastructure Score measures reported physical infrastructure only. It
does not measure reliability, uptime, availability, session success, wait
times, pricing, amenities, app quality, customer support, or compatibility for
a specific vehicle. NLR power and connector data can be incomplete or refreshed
differently by network. Visible methodology and attribution text makes these
limits explicit and does not imply NLR or DOE endorsement.
