#!/bin/sh
set -eu

# This container syncs Homepage config from the image (/seed) into a persistent
# named volume mounted at /out. Intended for Dokploy deployments where:
# - git is the source of truth
# - no host bind mounts are used
#
# Behavior:
# - OVERWRITE=true  => overwrite existing files in the volume on every start
# - OVERWRITE=false => only seed missing files (do not overwrite)

SEED_DIR="${SEED_DIR:-/seed}"
OUT_DIR="${OUT_DIR:-/out}"
OVERWRITE="${OVERWRITE:-true}"

log() { printf '%s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[ -d "$SEED_DIR" ] || fail "Seed directory not found: $SEED_DIR"
[ -d "$OUT_DIR" ] || fail "Output directory not found/mounted: $OUT_DIR"

log "[homepage-config-init] Seed: $SEED_DIR"
log "[homepage-config-init] Out : $OUT_DIR"
log "[homepage-config-init] OVERWRITE=$OVERWRITE"

# Ensure destination exists
mkdir -p "$OUT_DIR"

# Copy strategy:
# - We copy the CONTENTS of $SEED_DIR into $OUT_DIR (not nesting /seed).
# - Prefer tar streaming to preserve structure and avoid issues with dotfiles.
#
# Overwrite mode:
# - If overwriting, we do a clean replace of known config files/dirs by copying
#   over them. We do not blindly delete $OUT_DIR to avoid nuking unexpected
#   runtime artifacts that might also live there.
#
# Seed-only mode:
# - We copy only files that do not exist yet.

copy_all_overwrite() {
  # Copy everything from seed into out, overwriting existing files.
  # Using tar preserves dotfiles and directory structure.
  (cd "$SEED_DIR" && tar -cf - .) | (cd "$OUT_DIR" && tar -xpf -)
}

copy_only_missing() {
  # For seed-only mode we can't use tar directly (it would overwrite).
  # Instead, iterate and copy only missing paths.
  #
  # Use find with -print0 to handle weird filenames safely.
  # We recreate directories before copying files.
  find "$SEED_DIR" -mindepth 1 -print0 | while IFS= read -r -d '' src; do
    rel="${src#"$SEED_DIR"/}"
    dst="$OUT_DIR/$rel"

    if [ -d "$src" ]; then
      mkdir -p "$dst"
      continue
    fi

    # Ensure parent dir exists
    mkdir -p "$(dirname "$dst")"

    if [ -e "$dst" ]; then
      continue
    fi

    cp -p "$src" "$dst"
  done
}

case "$OVERWRITE" in
  true|TRUE|1|yes|YES)
    log "[homepage-config-init] Syncing (overwrite mode)..."
    copy_all_overwrite
    ;;
  false|FALSE|0|no|NO)
    log "[homepage-config-init] Syncing (seed-only mode, no overwrites)..."
    copy_only_missing
    ;;
  *)
    fail "Invalid OVERWRITE value: $OVERWRITE (expected true/false)"
    ;;
esac

log "[homepage-config-init] Sync complete."
# Exit cleanly so dependent services can start
exit 0
