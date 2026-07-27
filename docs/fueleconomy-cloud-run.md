# FuelEconomy.gov catalog operations

Evolve keeps a local copy of EPA vehicle data in PostgreSQL. Web requests never
depend on FuelEconomy.gov being available.

## Local commands

Apply the schema migration:

```bash
python manage.py migrate
```

Validate the current FuelEconomy.gov download without writing:

```bash
python manage.py sync_fueleconomy --dry-run
```

Synchronize the catalog:

```bash
python manage.py sync_fueleconomy
```

The command aborts before writing if the source schema changes, the download
fails, or fewer than 100 valid battery-electric records are present. Inserts,
updates, and stale-record deactivation run in one database transaction.

## Production resources

The production setup uses the existing `evolve-app` image and Cloud SQL
connection:

- Project: `portfolio-478704`
- Region: `us-central1`
- Service: `evolve-app`
- Cloud SQL connection: `portfolio-478704:us-central1:evolve-db`
- Migration job: `evolve-migrate`
- Catalog job: `evolve-sync-vehicles`

Both jobs must use the same service account, Cloud SQL attachment, and database
environment configuration as `evolve-app`.

The migration job command is:

```text
python manage.py migrate --noinput
```

The catalog job command is:

```text
python manage.py sync_fueleconomy
```

The initial job configuration can be created or refreshed without exposing
database credential values:

```bash
bash scripts/bootstrap-cloud-run-jobs.sh IMAGE_URL
```

Recommended catalog-job settings:

- Tasks: 1
- Retries: 1
- Timeout: 20 minutes
- Schedule: `0 3 * * 0`
- Time zone: `America/Chicago`

Run the catalog job manually once after the migration and before directing the
web service to the new table.

## Deployment pipeline

`cloudbuild.yaml` builds one immutable image, runs migrations, updates the
catalog job to that same image, and then deploys the web service. The two Cloud
Run jobs must be bootstrapped once before using that pipeline.

The pipeline intentionally does not create or replace database credentials.
Job secrets and environment values are configured once in Cloud Run and are
preserved when the pipeline updates only the image.

After bootstrap, submit manually with:

```bash
gcloud builds submit \
  --project portfolio-478704 \
  --region us-central1 \
  --config cloudbuild.yaml
```

For GitHub deployment, point the repository trigger at `cloudbuild.yaml`. A
successful push will then:

1. Build and push the application image.
2. Update and execute `evolve-migrate`.
3. Update `evolve-sync-vehicles`.
4. Deploy `evolve-app`.

The weekly Cloud Scheduler trigger invokes `evolve-sync-vehicles` independently
of application deployments.
