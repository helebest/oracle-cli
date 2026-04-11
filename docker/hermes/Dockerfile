FROM nousresearch/hermes-agent:latest

# P1: essential system tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl wget git jq tmux unzip openssh-client \
        gh vim cargo poppler-utils && \
    rm -rf /var/lib/apt/lists/* && \
    ln -sf /usr/bin/python3 /usr/bin/python

# P2: dev tools & Python utilities
RUN pip install --no-cache-dir --break-system-packages \
        yt-dlp ruff mypy pygount nano-pdf
