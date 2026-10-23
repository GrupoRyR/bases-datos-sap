<?php

namespace App\Modules\Panel\Providers;

use App\Support\Modules\ModuleServiceProvider;

/**
 * Panel: the TI panel (docs/plan-bases-sap.md, sections 2 and 6).
 * Owner: the «Panel» session.
 *
 * Web routes: /panel/*, named panel.*.
 * API routes: /api/panel/*, named panel.api.*.
 * Migrations: 2026_11_03_*. It may use Core and Sap contracts.
 */
final class PanelServiceProvider extends ModuleServiceProvider
{
    //
}
