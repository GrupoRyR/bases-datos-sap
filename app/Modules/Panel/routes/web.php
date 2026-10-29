<?php

// Panel web routes. PanelServiceProvider adds the "web" middleware, the
// /panel prefix and the "panel." route-name prefix: Route::get('/', ...)
// ->name('estado') becomes GET /panel named panel.estado. Every screen needs
// a role (core.consultar); screens that change data also need
// can:core.administrar on their own route.

use App\Modules\Panel\Http\Controllers\RequestHistoryController;
use App\Modules\Panel\Http\Controllers\StatusController;
use Illuminate\Support\Facades\Route;

Route::middleware(['auth', 'can:core.consultar'])->group(function () {
    Route::get('/', StatusController::class)->name('estado');
    Route::get('solicitudes', RequestHistoryController::class)->name('solicitudes');
});
