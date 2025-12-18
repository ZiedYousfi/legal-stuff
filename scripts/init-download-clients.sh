#!/bin/sh
set -e

wait_for_service() {
  local url="$1"
  local max_attempts=100
  local attempt=1
  
  echo "Waiting for $url..."
  while [ $attempt -le $max_attempts ]; do
    if curl -sf "$url" > /dev/null 2>&1; then
      echo "$url is ready!"
      return 0
    fi
    echo "Attempt $attempt/$max_attempts..."
    sleep 2
    attempt=$((attempt + 1))
  done
  echo "Timeout waiting for $url"
  return 1
}

add_qbittorrent() {
  local service="$1"
  local api_url="$2"
  local api_key="$3"
  local category="$4"
  local api_version="$5"

  existing=$(curl -sf "${api_url}/api/${api_version}/downloadclient" \
    -H "X-Api-Key: ${api_key}" | grep -c "qBittorrent" || true)

  if [ "$existing" -gt 0 ]; then
    echo "${service}: qBittorrent already configured, skipping."
    return 0
  fi

  echo "${service}: Adding qBittorrent download client..."
  
  curl -sf -X POST "${api_url}/api/${api_version}/downloadclient" \
    -H "X-Api-Key: ${api_key}" \
    -H "Content-Type: application/json" \
    -d '{
      "name": "qBittorrent",
      "implementation": "QBittorrent",
      "configContract": "QBittorrentSettings",
      "protocol": "torrent",
      "enable": true,
      "priority": 1,
      "removeCompletedDownloads": false,
      "removeFailedDownloads": true,
      "fields": [
        {"name": "host", "value": "qbittorrent"},
        {"name": "port", "value": 8080},
        {"name": "useSsl", "value": false},
        {"name": "username", "value": "'"${QBIT_USER}"'"},
        {"name": "password", "value": "'"${QBIT_PASS}"'"},
        {"name": "category", "value": "'"${category}"'"},
        {"name": "initialState", "value": 0},
        {"name": "sequentialOrder", "value": false},
        {"name": "firstAndLast", "value": false}
      ]
    }'
  
  echo "${service}: Done!"
}

wait_for_service "http://sonarr:8989/api/v3/system/status?apiKey=${SONARR_API_KEY}"
wait_for_service "http://radarr:7878/api/v3/system/status?apiKey=${RADARR_API_KEY}"
wait_for_service "http://prowlarr:9696/api/v1/system/status?apiKey=${PROWLARR_API_KEY}"

add_qbittorrent "Sonarr" "http://sonarr:8989" "$SONARR_API_KEY" "sonarr" "v3"
add_qbittorrent "Radarr" "http://radarr:7878" "$RADARR_API_KEY" "radarr" "v3"
add_qbittorrent "Prowlarr" "http://prowlarr:9696" "$PROWLARR_API_KEY" "prowlarr" "v1"

echo "All download clients configured!"