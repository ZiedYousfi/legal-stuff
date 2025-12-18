#!/bin/sh
set -eu

wait_for() {
  url="$1"
  tries="${2:-60}"
  i=1
  while [ "$i" -le "$tries" ]; do
    if curl -sf "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
    i=$((i + 1))
  done
  echo "Timeout waiting for: $url" >&2
  return 1
}

RADARR_URL="http://radarr:7878"
NAMING_URL="${RADARR_URL}/api/v3/config/naming"

wait_for "${RADARR_URL}/api/v3/system/status?apiKey=${RADARR_API_KEY}" 60

cfg="$(curl -sf -H "X-Api-Key: ${RADARR_API_KEY}" "${NAMING_URL}")"
current="$(echo "$cfg" | jq -r '.colonReplacementFormat')"

echo "Radarr colonReplacementFormat currently: ${current}"

# Valeurs acceptées par ton buildarr-radarr/radarr-py:
# delete | dash | spaceDash | spaceDashSpace
if [ "$current" = "dash" ]; then
  echo "Radarr naming OK, nothing to do."
  exit 0
fi

new_cfg="$(echo "$cfg" | jq '.colonReplacementFormat = "dash"')"

curl -sf -X PUT \
  -H "X-Api-Key: ${RADARR_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "$new_cfg" \
  "${NAMING_URL}" >/dev/null

echo "Radarr naming patched to colonReplacementFormat=dash"