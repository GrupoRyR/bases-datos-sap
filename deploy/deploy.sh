#!/usr/bin/env bash
#
# Routine deploy of Bases de datos SAP on cPanel (GoDaddy). It runs ON THE SERVER over SSH:
#
#   cd ~/<app-folder> && bash deploy/deploy.sh
#
# Template taken from Portal RYR. Safe to run as many times as needed. The CSS/JS assets
# arrive already compiled in public/build because the server has no Node. It holds no
# secrets: everything sensitive lives in the server's .env.
#
# Optional variables:
#   PHP=/usr/local/bin/php                 PHP binary (use the same one as the account's cron jobs)
#   COMPOSER_BIN="php ~/composer.phar"     Composer command when `composer` does not exist
#
# COMPOSER_BIN is used instead of COMPOSER because Composer reads the COMPOSER variable
# as the name of the composer.json file.
#
# Project choices:
#   - No `storage:link`: the app never uses the `public` disk.
#   - No `queue:restart`: the app queues no jobs.

set -euo pipefail

# Always work from the project root, wherever the script is called from.
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PHP="${PHP:-php}"
COMPOSER_BIN="${COMPOSER_BIN:-composer}"

log() {
    printf '\n==> %s\n' "$1"
}

bring_up() {
    log "Bringing the application back up"
    "$PHP" artisan up || true
}

# On the first install there is no vendor/ yet, so maintenance mode is not available.
if [ -f vendor/autoload.php ]; then
    log "Entering maintenance mode"
    "$PHP" artisan down --retry=60
fi

# Whatever happens from here on, the site must not stay in maintenance mode.
trap bring_up EXIT

log "Pulling latest code"
git pull --ff-only

log "Installing PHP dependencies"
# shellcheck disable=SC2086 # COMPOSER_BIN may be "php composer.phar" on purpose.
$COMPOSER_BIN install --no-dev --optimize-autoloader --no-interaction

# One migrate covers the four databases (app, maestros, cartera and ventas): each migration
# declares its own connection. The databases themselves are created beforehand in cPanel.
log "Running database migrations"
"$PHP" artisan migrate --force

log "Caching config, routes, views and events"
"$PHP" artisan optimize

trap - EXIT
bring_up

log "Deploy finished"
