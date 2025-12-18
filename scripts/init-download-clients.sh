#!/bin/sh
set -euo pipefail

# Check for required tools
if ! command -v jq >/dev/null 2>&1; then
  echo "[ERROR] jq is required but not installed. Exiting."
  exit 1
fi

log() {
  echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

wait_for_service() {
  local service_name="$1"
  local url="$2"
  local max_attempts=60
  local attempt=1

  log "Waiting for ${service_name} to be ready at ${url}..."
  while [ $attempt -le $max_attempts ]; do
    if curl -sf "$url" > /dev/null; then
      log "${service_name} is ready!"
      return 0
    fi
    log "Attempt ${attempt}/${max_attempts}: ${service_name} not reachable yet. Sleeping 10s..."
    sleep 10
    attempt=$((attempt + 1))
  done
  log "Timeout waiting for ${service_name}"
  return 1
}

add_qbittorrent() {
  local service="$1"
  local api_url="$2"
  local api_key="$3"
  local category="$4"
  local api_version="$5"

  log "${service}: Checking for existing qBittorrent configuration..."

  local tmp_res
  tmp_res=$(mktemp)
  local status_code

  # Fetch existing clients
  if ! status_code=$(curl -s -o "$tmp_res" -w "%{http_code}" \
    "${api_url}/api/${api_version}/downloadclient" \
    -H "X-Api-Key: ${api_key}"); then
    log "${service}: Error - Curl command failed to execute."
    rm -f "$tmp_res"
    return 1
  fi

  local response
  response=$(cat "$tmp_res")
  rm -f "$tmp_res"

  if [ "$status_code" -ne 200 ]; then
    log "${service}: Error fetching clients (Status: ${status_code}). Response: ${response}"
    return 1
  fi

  # Robust check using jq to look for QBittorrent implementation
  local count
  count=$(echo "$response" | jq '[.[] | select(.implementation == "QBittorrent")] | length')

  if [ "$count" -gt 0 ]; then
    log "${service}: qBittorrent already configured (found ${count} instance(s)). Skipping initialization."
    return 0
  fi

  log "${service}: Adding qBittorrent download client..."

  # Constructing JSON payload safely
  local payload
  payload=$(jq -n \
    --arg name "qBittorrent" \
    --arg impl "QBittorrent" \
    --arg contract "QBittorrentSettings" \
    --arg proto "torrent" \
    --arg host "qbittorrent" \
    --argjson port 8080 \
    --arg user "${QBIT_USER}" \
    --arg pass "${QBIT_PASS}" \
    --arg cat "${category}" \
    '{
      name: $name,
      implementation: $impl,
      configContract: $contract,
      protocol: $proto,
      enable: true,
      priority: 1,
      removeCompletedDownloads: false,
      removeFailedDownloads: true,
      fields: [
        {name: "host", value: $host},
        {name: "port", value: $port},
        {name: "useSsl", value: false},
        {name: "username", value: $user},
        {name: "password", value: $pass},
        {name: "category", value: $cat},
        {name: "initialState", value: 0},
        {name: "sequentialOrder", value: false},
        {name: "firstAndLast", value: false}
      ]
    }')

  tmp_res=$(mktemp)
  if ! status_code=$(curl -s -o "$tmp_res" -w "%{http_code}" \
    -X POST "${api_url}/api/${api_version}/downloadclient" \
    -H "X-Api-Key: ${api_key}" \
    -H "Content-Type: application/json" \
    -d "$payload"); then
    log "${service}: Error - Curl POST command failed to execute."
    rm -f "$tmp_res"
    return 1
  fi

  response=$(cat "$tmp_res")
  rm -f "$tmp_res"

  if [ "$status_code" -ge 200 ] && [ "$status_code" -lt 300 ]; then
    log "${service}: Successfully added qBittorrent!"
  else
    log "${service}: Failed to add qBittorrent configuration (Status: ${status_code})."
    log "${service}: API Response: ${response}"
    return 1
  fi
}

# Wait for services to be healthy
wait_for_service "Sonarr" "http://sonarr:8989/api/v3/system/status?apiKey=${SONARR_API_KEY}"
wait_for_service "Radarr" "http://radarr:7878/api/v3/system/status?apiKey=${RADARR_API_KEY}"
wait_for_service "Prowlarr" "http://prowlarr:9696/api/v1/system/status?apiKey=${PROWLARR_API_KEY}"
wait_for_service "qBittorrent" "http://qbittorrent:8080/"

# Initialize download clients
add_qbittorrent "Sonarr" "http://sonarr:8989" "$SONARR_API_KEY" "sonarr" "v3"
add_qbittorrent "Radarr" "http://radarr:7878" "$RADARR_API_KEY" "radarr" "v3"
#add_qbittorrent "Prowlarr" "http://prowlarr:9696" "$PROWLARR_API_KEY" "prowlarr" "v1"

log "All download client initializations completed!"
