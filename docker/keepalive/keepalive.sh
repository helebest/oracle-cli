#!/bin/sh
set -e

LOG_PREFIX="[keepalive]"
HEALTH_INTERVAL=300    # 5 minutes
ZOMBIE_INTERVAL=1800   # 30 minutes
DISK_INTERVAL=3600     # 1 hour
CPU_INTERVAL=1200      # 20 minutes
CPU_DURATION=180       # 3 minutes burst
LOOP_INTERVAL=60       # main loop tick: 1 minute

last_health=0
last_zombie=0
last_disk=0
last_cpu=0

log() {
    echo "$(TZ=Asia/Shanghai date '+%Y-%m-%d %H:%M:%S %Z') $LOG_PREFIX $*"
}

# --- Task 1: CPU keepalive (every 20 min, 3 min burst) ---
cpu_keepalive() {
    log "CPU burst: starting ${CPU_DURATION}s workload"
    timeout "$CPU_DURATION" sh -c 'while true; do head -c 1M /dev/urandom | sha256sum > /dev/null; done' 2>/dev/null || true
    log "CPU burst: done"
}

# --- Task 3: Container health check ---
check_container() {
    name=$1
    url=$2
    status=$(docker inspect --format='{{.State.Status}}' "$name" 2>/dev/null || echo "not_found")

    if [ "$status" != "running" ]; then
        log "WARN: $name is $status, restarting..."
        docker restart "$name" 2>/dev/null || log "ERROR: failed to restart $name"
        return
    fi

    # HTTP health check if URL provided
    if [ -n "$url" ]; then
        if ! curl -sf --connect-timeout 5 --max-time 10 "$url" > /dev/null 2>&1; then
            log "WARN: $name HTTP check failed ($url), restarting..."
            docker restart "$name" 2>/dev/null || log "ERROR: failed to restart $name"
            return
        fi
    fi

    log "OK: $name running"
}

health_check() {
    log "--- Health check ---"
    check_container "3x-ui" "http://localhost:2053"
    check_container "hermes" ""
    check_container "caddy" "http://localhost:80"
}

# --- Task 4: Zombie process cleanup ---
zombie_cleanup() {
    zombie_count=$(ps aux 2>/dev/null | grep -w Z | grep -v grep | wc -l)
    if [ "$zombie_count" -gt 5 ]; then
        log "WARN: $zombie_count zombie processes found, restarting hermes..."
        docker restart hermes 2>/dev/null || log "ERROR: failed to restart hermes"
    else
        log "Zombies: $zombie_count (OK)"
    fi
}

# --- Task 5: Disk space monitor ---
disk_monitor() {
    usage=$(df / | tail -1 | awk '{print $5}' | tr -d '%')
    log "Disk usage: ${usage}%"
    if [ "$usage" -gt 80 ]; then
        log "WARN: disk usage ${usage}% > 80%, pruning Docker..."
        docker system prune -f 2>/dev/null | tail -1
    fi
}

# --- Main loop ---
log "Starting keepalive service"
log "Health check interval: ${HEALTH_INTERVAL}s"
log "Zombie cleanup interval: ${ZOMBIE_INTERVAL}s"
log "Disk monitor interval: ${DISK_INTERVAL}s"
log "CPU burst: ${CPU_DURATION}s every ${CPU_INTERVAL}s"

# Run health check immediately on start
health_check
last_health=$(date +%s)

while true; do
    now=$(date +%s)

    # CPU keepalive (every 20 min)
    elapsed=$((now - last_cpu))
    if [ "$elapsed" -ge "$CPU_INTERVAL" ]; then
        cpu_keepalive
        last_cpu=$now
    fi

    # Health check (every 5 min)
    elapsed=$((now - last_health))
    if [ "$elapsed" -ge "$HEALTH_INTERVAL" ]; then
        health_check
        last_health=$now
    fi

    # Zombie cleanup (every 30 min)
    elapsed=$((now - last_zombie))
    if [ "$elapsed" -ge "$ZOMBIE_INTERVAL" ]; then
        zombie_cleanup
        last_zombie=$now
    fi

    # Disk monitor (every hour)
    elapsed=$((now - last_disk))
    if [ "$elapsed" -ge "$DISK_INTERVAL" ]; then
        disk_monitor
        last_disk=$now
    fi

    sleep "$LOOP_INTERVAL"
done
