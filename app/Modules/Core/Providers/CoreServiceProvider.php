<?php

namespace App\Modules\Core\Providers;

use App\Modules\Core\Contracts\AuditLogger;
use App\Modules\Core\Infrastructure\Audit\DatabaseAuditLogger;
use App\Support\Modules\ModuleServiceProvider;

/**
 * Core: sign-in, users and roles, the audit log and the layout
 * (docs/plan-bases-sap.md, section 9). Owner: the «cimientos» session.
 *
 * Web routes: / (site root), named core.*.
 * API routes: /api/core/*, named core.api.*.
 * Migrations: 2026_11_01_*. Core depends on no other module.
 */
final class CoreServiceProvider extends ModuleServiceProvider
{
    /**
     * Core serves the site root: the sign-in page and the home.
     */
    protected function webPrefix(): string
    {
        return '';
    }

    protected function registerModule(): void
    {
        // Reads the signed-in user and the request, so one per request (or job).
        $this->app->scoped(AuditLogger::class, DatabaseAuditLogger::class);
    }
}
