<?php

// Panel web routes. PanelServiceProvider adds the "web" middleware, the
// /panel prefix and the "panel." route-name prefix: Route::get('/', ...)
// ->name('estado') becomes GET /panel named panel.estado. Every screen needs
// a role (core.consultar); screens that change data, and the lookup of
// personal data (Ley 1581), also need can:core.administrar.

use App\Modules\Panel\Http\Controllers\ConnectedAppsController;
use App\Modules\Panel\Http\Controllers\LookupController;
use App\Modules\Panel\Http\Controllers\RequestHistoryController;
use App\Modules\Panel\Http\Controllers\StatusController;
use App\Modules\Panel\Http\Controllers\UpdateDataController;
use Illuminate\Support\Facades\Route;

Route::middleware(['auth', 'can:core.consultar'])->group(function () {
    Route::get('/', StatusController::class)->name('estado');
    Route::get('solicitudes', RequestHistoryController::class)->name('solicitudes');

    Route::middleware('can:core.administrar')->group(function () {
        // The term travels only in the POST body (Ley 1581); the GET is the empty form.
        Route::get('consulta', [LookupController::class, 'create'])->name('consulta');
        Route::post('consulta', [LookupController::class, 'search'])->name('consulta.buscar');

        Route::get('actualizar', [UpdateDataController::class, 'create'])->name('actualizar');
        Route::post('actualizar', [UpdateDataController::class, 'store'])->name('actualizar.store');

        // A new or rotated key comes back once, in the POST response itself.
        Route::get('apps', [ConnectedAppsController::class, 'index'])->name('apps');
        Route::post('apps', [ConnectedAppsController::class, 'store'])->name('apps.store');
        Route::post('apps/{app}/llave', [ConnectedAppsController::class, 'rotate'])->where('app', '[0-9]{1,9}')->name('apps.rotate');
        Route::post('apps/{app}/revocar', [ConnectedAppsController::class, 'revoke'])->where('app', '[0-9]{1,9}')->name('apps.revoke');
    });
});
