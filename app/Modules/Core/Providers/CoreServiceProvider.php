<?php

namespace App\Modules\Core\Providers;

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
}
