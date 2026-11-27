#!/usr/bin/env bash
#
# Forced-command dispatcher for the Bases de datos SAP deploy key. It runs ON THE SERVER and
# is the only entry point of that key: its line in ~/.ssh/authorized_keys looks like
#
#   restrict,command="bash ~/bases-sap/deploy/despachar.sh" ssh-ed25519 AAAA... bases-sap-deploy
#
# so sshd ignores whatever the client asks to run and starts this script instead, with the
# client's request in $SSH_ORIGINAL_COMMAND. Only this closed list of orders is accepted:
#
#   ping                   prints "ok"
#   pendientes             migrations not run yet (artisan migrate:status --pending)
#   puede-desplegar        artisan sap:puede-desplegar, exit code passed through
#   previsualizar <sha>    lists and counts the migrations <sha> adds compared with HEAD; never migrates
#   desplegar <sha>        fast-forwards to <sha>, which must already be on origin/main, with deploy/deploy.sh
#   estado                 HEAD, maintenance mode and today's errors in the log
#
# The request is never evaluated: it must match a strict character set, then it is split
# into words and matched word by word. This script never reads, prints or sources .env.
#
# Exit codes: 64 order not allowed, 65 commit refused, 70 HEAD did not land on <sha>,
# 75 try again later (lock held or sap:puede-desplegar refused).
#
# Overrides, for tests only: BASES_SAP_APP_DIR (default: the folder above this script),
# PHP (default php) and DEPLOY_SCRIPT (default deploy/deploy.sh, relative to the app).

set -euo pipefail

APP_DIR="${BASES_SAP_APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PHP="${PHP:-php}"
DEPLOY_SCRIPT="${DEPLOY_SCRIPT:-deploy/deploy.sh}"
LOCK_DIR="$APP_DIR/storage/despachar.lock"

refuse() { # <exit code> <message>
    printf '%s\n' "$2" >&2
    exit "$1"
}

not_allowed() { # [detail]
    refuse 64 "order not allowed${1:+: $1}"
}

require_sha() {
    [[ "$1" =~ ^[0-9a-f]{40}$ ]] || not_allowed "invalid sha"
}

previsualizar() {
    local sha="$1" files count=0
    require_sha "$sha"

    git fetch --quiet origin main
    git cat-file -e "$sha^{commit}" 2>/dev/null || refuse 65 "unknown commit: $sha"

    files="$(git diff --name-only --diff-filter=A HEAD "$sha" -- '*/migrations/*' 'database/migrations/*')"
    if [ -n "$files" ]; then
        printf '%s\n' "$files"
        count="$(printf '%s\n' "$files" | wc -l | tr -d ' ')"
    fi

    printf 'migrations: %s\n' "$count"
}

release_lock() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}

desplegar() {
    local sha="$1" previous head
    require_sha "$sha"

    # mkdir is atomic: only one deploy gets the lock. The trap is set only once this run owns it.
    mkdir "$LOCK_DIR" 2>/dev/null || refuse 75 "deploy already running (lock: storage/despachar.lock)"
    trap release_lock EXIT

    git fetch --quiet origin main

    # The deploy key is a repository secret (GitHub Free), so any workflow could send any sha.
    # The server only accepts commits that are already on main.
    git merge-base --is-ancestor "$sha" origin/main 2>/dev/null \
        || refuse 65 "commit is not on origin/main: $sha"

    previous="$(git rev-parse HEAD)"
    if [ "$previous" = "$sha" ]; then
        printf 'already deployed: %s\n' "$sha"
        exit 0
    fi

    git merge-base --is-ancestor "$previous" "$sha" \
        || refuse 65 "commit is not a fast-forward of HEAD ($previous): $sha"

    "$PHP" artisan sap:puede-desplegar --no-ansi \
        || refuse 75 "sap:puede-desplegar refused the deploy, try again later"

    printf 'previous: %s\n' "$previous"

    DEPLOY_REF="$sha" bash "$DEPLOY_SCRIPT"

    head="$(git rev-parse HEAD)"
    [ "$head" = "$sha" ] || refuse 70 "HEAD is $head after the deploy, expected $sha"

    printf 'deployed: %s\n' "$sha"
    printf 'to revert: git revert %s on main, then desplegar the new main commit (previous: %s)\n' "$sha" "$previous"
}

estado() {
    local today pattern count=0 file
    local logs=()

    printf 'head: %s\n' "$(git rev-parse HEAD)"

    if [ -e storage/framework/down ]; then
        echo 'maintenance: on'
    else
        echo 'maintenance: off'
    fi

    # The daily channel writes laravel-<date>.log; the single channel, laravel.log.
    today="$(date +%Y-%m-%d)"
    for file in "storage/logs/laravel-$today.log" storage/logs/laravel.log; do
        if [ -f "$file" ]; then
            logs+=("$file")
        fi
    done

    # Laravel's line format: [2026-11-27 10:00:00] production.ERROR: message
    pattern="^\[$today[^]]*] [^ ]+\.ERROR:"
    if [ "${#logs[@]}" -gt 0 ]; then
        count="$({ grep -h -E "$pattern" "${logs[@]}" || true; } | wc -l | tr -d ' ')"
    fi

    printf 'errors today: %s\n' "$count"

    if [ "$count" -gt 0 ]; then
        { grep -h -E "$pattern" "${logs[@]}" || true; } | tail -n 5 | cut -c1-200
    fi
}

order="${SSH_ORIGINAL_COMMAND:-}"

# Lowercase letters, digits and hyphens, single spaces between words: no shell metacharacter,
# quote, glob, tab or newline gets past this check.
[[ "$order" =~ ^[a-z0-9-]+( [a-z0-9-]+)*$ ]] || not_allowed

read -r -a words <<< "$order"

cd "$APP_DIR"

case "${words[0]} ${#words[@]}" in
    'ping 1') echo ok ;;
    'pendientes 1') exec "$PHP" artisan migrate:status --pending --no-ansi ;;
    'puede-desplegar 1') exec "$PHP" artisan sap:puede-desplegar --no-ansi ;;
    'previsualizar 2') previsualizar "${words[1]}" ;;
    'desplegar 2') desplegar "${words[1]}" ;;
    'estado 1') estado ;;
    *) not_allowed ;;
esac
