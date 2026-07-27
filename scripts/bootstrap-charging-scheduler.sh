#!/usr/bin/env bash
set -euo pipefail

project_id="portfolio-478704"
region="us-central1"
job_name="evolve-refresh-charging"
scheduler_name="evolve-refresh-charging-daily"
service_account="405148685226-compute@developer.gserviceaccount.com"
schedule="${1:-20 3 * * *}"
time_zone="${2:-America/Chicago}"
uri="https://run.googleapis.com/v2/projects/${project_id}/locations/${region}/jobs/${job_name}:run"

gcloud run jobs add-iam-policy-binding "${job_name}" \
    --project "${project_id}" \
    --region "${region}" \
    --member "serviceAccount:${service_account}" \
    --role "roles/run.invoker" \
    --quiet > /dev/null

if gcloud scheduler jobs describe "${scheduler_name}" \
    --project "${project_id}" \
    --location "${region}" > /dev/null 2>&1; then
    action="update"
else
    action="create"
fi

gcloud scheduler jobs "${action}" http "${scheduler_name}" \
    --project "${project_id}" \
    --location "${region}" \
    --schedule "${schedule}" \
    --time-zone "${time_zone}" \
    --uri "${uri}" \
    --http-method POST \
    --oauth-service-account-email "${service_account}" \
    --quiet
