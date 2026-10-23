<?php

namespace App\Modules\Sap\Providers;

use App\Support\Modules\ModuleServiceProvider;

/**
 * Sap: the MAESTROS and CARTERA data, the robot ingest (runs and batches),
 * update requests and the API the apps call (docs/plan-bases-sap.md,
 * sections 2 and 4). Owner: the «Datos y API» session.
 *
 * Web routes: /sap/*, named sap.*.
 * API routes: /api/sap/*, named sap.api.*.
 * Migrations: 2026_11_02_*. It may use only Core contracts.
 */
final class SapServiceProvider extends ModuleServiceProvider
{
    //
}
