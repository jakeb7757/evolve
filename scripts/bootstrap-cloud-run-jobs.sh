#!/usr/bin/env bash
set -euo pipefail
umask 077

project_id="portfolio-478704"
region="us-central1"
service_name="evolve-app"
service_account="405148685226-compute@developer.gserviceaccount.com"
cloud_sql_instance="portfolio-478704:us-central1:evolve-db"
image="${1:-}"

task_dir="$(mktemp -d)"
service_json="${task_dir}/service.json"
environment_json="${task_dir}/environment.json"

cleanup() {
    rm -f "${service_json}" "${environment_json}"
    rmdir "${task_dir}"
}
trap cleanup EXIT

# Copy the existing service environment without printing credential values or
# storing them in the repository.
gcloud run services describe "${service_name}" \
    --project "${project_id}" \
    --region "${region}" \
    --format=json > "${service_json}"

if [[ -z "${image}" ]]; then
    image="$(jq -r '.spec.template.spec.containers[0].image' "${service_json}")"
fi
if [[ -z "${image}" || "${image}" == "null" ]]; then
    echo "Unable to determine the deployed ${service_name} image." >&2
    exit 1
fi

jq '
    [.spec.template.spec.containers[0].env[]
      | select(has("value"))
      | {key: .name, value: .value}]
    | from_entries
' "${service_json}" > "${environment_json}"

for required_key in SECRET_KEY DB_NAME DB_USER DB_PASSWORD DB_HOST; do
    jq --exit-status --arg key "${required_key}" 'has($key)' \
        "${environment_json}" > /dev/null
done

deploy_job() {
    local job_name="$1"
    local timeout="$2"
    shift 2
    local command_args=("$@")

    if gcloud run jobs describe "${job_name}" \
        --project "${project_id}" \
        --region "${region}" > /dev/null 2>&1; then
        action="update"
    else
        action="create"
    fi

    gcloud run jobs "${action}" "${job_name}" \
        --project "${project_id}" \
        --region "${region}" \
        --image "${image}" \
        --service-account "${service_account}" \
        --set-cloudsql-instances "${cloud_sql_instance}" \
        --env-vars-file "${environment_json}" \
        --command python \
        --args "$(IFS=,; echo "${command_args[*]}")" \
        --tasks 1 \
        --max-retries 1 \
        --task-timeout "${timeout}" \
        --quiet
}

deploy_job "evolve-migrate" "10m" manage.py migrate --noinput
deploy_job "evolve-sync-vehicles" "20m" manage.py sync_fueleconomy
deploy_job "evolve-refresh-charging" "30m" manage.py refresh_charging_networks
