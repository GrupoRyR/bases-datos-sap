<?php

use App\Modules\Sap\Http\Controllers\Robot\FailRunController;
use App\Modules\Sap\Http\Controllers\Robot\StartRunController;
use Illuminate\Support\Facades\Route;

/*
| Exact paths of docs/contrato-robot.md under /api (apiPrefix() is empty),
| named sap.api.*. Run ids are plain numbers, not bound models, so nothing
| is looked up before the signature checks out.
*/

Route::prefix('robot/v1')->name('robot.')->middleware('sap.robot')->group(function () {
    Route::post('corridas', StartRunController::class)->name('corridas.store');
    Route::post('corridas/{run}/fallar', FailRunController::class)->whereNumber('run')->name('corridas.fallar');
});
