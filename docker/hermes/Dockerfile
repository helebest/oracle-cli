# Single source of truth for the upstream pin. Override at build time with
# `--build-arg HERMES_VERSION=vX.Y.Z` (or via docker-compose build.args).
ARG HERMES_VERSION=v2026.5.7
FROM nousresearch/hermes-agent:${HERMES_VERSION}

# ARG before FROM is only visible to FROM; re-declare so subsequent layers
# (LABEL, RUN) can see it.
ARG HERMES_VERSION

# OCI-standard labels so `docker inspect hermes-agent:${HERMES_VERSION}`
# records exactly which upstream release this image was built on top of.
LABEL org.opencontainers.image.title="hermes-agent (oracle-cli custom)" \
      org.opencontainers.image.version="${HERMES_VERSION}" \
      org.opencontainers.image.base.name="docker.io/nousresearch/hermes-agent:${HERMES_VERSION}" \
      org.opencontainers.image.source="https://github.com/NousResearch/hermes-agent" \
      org.opencontainers.image.description="Hermes Agent with Docker CLI, gh, vim, and uv-installed Python tooling"

# Upstream toggles the trailing USER directive between releases:
#   v2026.4.16 → ends as root
#   v2026.4.23 → ends as hermes (rootless)
#   v2026.4.30 → ends as root, entrypoint uses tini + gosu to drop to hermes
#   v2026.5.7  → ends as root; gateway now REFUSES to start as root in the
#                official image (PR #21250), so the tini + gosu drop to UID
#                10000 is mandatory — DO NOT add a trailing `USER hermes` here.
# Pin to root for our build layers (apt + uv pip) and DO NOT switch back at the
# end — the upstream entrypoint expects to start as root for usermod/gosu.
USER root

# P1: essential system tools + Docker CLI
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl wget git jq tmux unzip openssh-client \
        gh vim cargo poppler-utils \
        ca-certificates gnupg && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin && \
    rm -rf /var/lib/apt/lists/* && \
    ln -sf /usr/bin/python3 /usr/bin/python

# P2: dev tools & Python utilities.
# --break-system-packages bypasses the PEP 668 EXTERNALLY-MANAGED marker that
# Debian-based images ship in Python 3.13+ (introduced by upstream on v2026.4.16).
RUN uv pip install --system --break-system-packages --no-cache \
        yt-dlp ruff mypy pygount nano-pdf jupyterlab
