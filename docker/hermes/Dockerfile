FROM nousresearch/hermes-agent:latest

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

# P2: dev tools & Python utilities
RUN pip install --no-cache-dir --break-system-packages \
        yt-dlp ruff mypy pygount nano-pdf jupyterlab
