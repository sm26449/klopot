#!/bin/sh
# Backup sidecar scheduler (the image's entrypoint, Dockerfile.backup).
#
# BACKUP_CRON is a "minute hour" expression; the day-of-month / month /
# day-of-week fields are accepted but only minute + hour are honoured (the
# daily backup is the use case). A field is `*`, a number (`2`, `02`) or a
# step (`*/15`). POSIX sh — no bashisms: `$((10#x))` dies under dash, and a
# step value broke it under bash too (review K26).
#
# Format: "<MIN> <HOUR> [* * *]" — e.g. "0 2 * * *" → 02:00 daily.

# _dec N — N without leading zeros, as a decimal ("08" → 8); fails unless N
# is all digits. Not `expr N + 0`: expr exits 1 when the result is 0.
_dec() {
    case "$1" in ""|*[!0-9]*) return 1 ;; esac
    n=$(printf '%s' "$1" | sed 's/^0*//')
    printf '%s\n' "${n:-0}"
}

# cron_field_matches FIELD VALUE — 0 (true) if VALUE (zero-padded or not)
# satisfies FIELD.
cron_field_matches() {
    value=$(_dec "$2") || return 1
    case "$1" in
        "*") return 0 ;;
        "*/"*)
            step=$(_dec "${1#\*/}") || return 1
            [ "$step" -gt 0 ] && [ $((value % step)) -eq 0 ]
            return ;;
        *)
            want=$(_dec "$1") || return 1
            [ "$want" -eq "$value" ]
            return ;;
    esac
}

run_scheduler() {
    set -eu
    : "${BACKUP_CRON:=0 2 * * *}"
    : "${BACKUP_DIR:=/backups}"
    mkdir -p "$BACKUP_DIR"

    cron_min=$(echo "$BACKUP_CRON" | awk '{print $1}')
    cron_hr=$(echo "$BACKUP_CRON" | awk '{print $2}')
    for f in "$cron_min" "$cron_hr"; do
        case "$f" in
            "*"|"*/"[0-9]*|[0-9]*) ;;
            *) echo "BACKUP_CRON field '$f' is not '*', a number or '*/N'" >&2; exit 2 ;;
        esac
    done

    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] sidecar starting; schedule=$cron_min $cron_hr * * *"

    # First-run sanity backup. Exit-code-tolerant — if MySQL isn't ready
    # yet the next scheduled tick will retry.
    /usr/local/bin/backup.sh >> "$BACKUP_DIR/backup.log" 2>&1 || \
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] initial backup failed; will retry on schedule"

    last_fire_key=""
    while true; do
        cur_min=$(date -u +%M)
        cur_hr=$(date -u +%H)
        # Date prefix so the dedup key resets each day: a key that survived
        # 24 h would block the next morning's run.
        cur_key="$(date -u +%Y-%m-%d)-$cur_hr-$cur_min"
        if cron_field_matches "$cron_min" "$cur_min" && cron_field_matches "$cron_hr" "$cur_hr" \
                && [ "$cur_key" != "$last_fire_key" ]; then
            /usr/local/bin/backup.sh >> "$BACKUP_DIR/backup.log" 2>&1 || \
                echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] scheduled backup failed"
            last_fire_key="$cur_key"
        fi
        sleep 30
    done
}

# Sourced by the tests with BACKUP_SCHEDULER_LIB=1 to reach the helper only.
if [ "${BACKUP_SCHEDULER_LIB:-}" != 1 ]; then
    run_scheduler
fi
