FROM nousresearch/hermes-agent:v2026.4.30

# Upstream toggles the trailing USER directive between releases:
#   v2026.4.16 → ends as root
#   v2026.4.23 → ends as hermes (rootless)
#   v2026.4.30 → ends as root, entrypoint uses tini + gosu to drop to hermes
# Pin to root for our build layers (apt + uv pip) and DO NOT switch back at the
# end — v2026.4.30's entrypoint expects to start as root for usermod/gosu.
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
