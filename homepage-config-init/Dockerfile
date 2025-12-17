# Init container image used to sync Homepage config from this git repo into
# the persistent Docker named volume (mounted at /out).
#
# This image is meant to be built by Dokploy from this repository.
# It does NOT run Homepage. It only copies config files into the volume and exits.

FROM alpine:3.20

# Minimal tools for a safe copy routine (mkdir/cp/ls are in busybox; we add coreutils
# for consistent flags/behavior across environments).
RUN apk add --no-cache coreutils

# The git-tracked Homepage config directory (from this repo) will be copied into the image.
# We keep it under /seed and then copy into the persistent volume at runtime.
WORKDIR /seed
COPY homepage/ /seed/

# Runtime destination is expected to be a mounted volume.
# - /out will be the `homepage_config` named volume mounted by docker-compose.
# - /seed is baked into the image from git.
ENV SEED_DIR=/seed \
    OUT_DIR=/out \
    # If true, git is the source of truth and we overwrite existing files in the volume.
    # If false, we only seed missing files (no overwrites).
    OVERWRITE=true

# Copy script (kept in this image; executed as container entrypoint)
COPY homepage-config-init/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
