<?php

// Core web routes. CoreServiceProvider adds the "web" middleware, no URL
// prefix (Core serves the site root) and the "core." route-name prefix:
// Route::get('login', ...)->name('login') becomes GET /login named core.login.

use App\Modules\Core\Http\Controllers\Auth\LoginController;
use App\Modules\Core\Http\Controllers\Auth\LogoutController;
use App\Modules\Core\Http\Controllers\Auth\MicrosoftCallbackController;
use App\Modules\Core\Http\Controllers\Auth\MicrosoftRedirectController;
use App\Modules\Core\Http\Controllers\Dev\DemoLoginController;
use App\Modules\Core\Http\Controllers\HomeController;
use App\Modules\Core\Http\Controllers\NoAccessController;
use Illuminate\Support\Facades\Route;

Route::middleware('guest')->group(function () {
    Route::get('login', LoginController::class)->name('login');
    Route::get('auth/microsoft', MicrosoftRedirectController::class)->name('auth.redirect');
    // Must match MICROSOFT_REDIRECT_URI.
    Route::get('auth/microsoft/callback', MicrosoftCallbackController::class)->name('auth.callback');
});

Route::middleware('auth')->group(function () {
    Route::get('/', HomeController::class)->name('inicio');
    Route::get('sin-acceso', NoAccessController::class)->name('sin-acceso');
    Route::post('logout', LogoutController::class)->name('logout');
});

// Only in local: sign in as a demo user without Microsoft. The routes do not
// even exist in another environment; the controller also checks the
// environment and that the request comes from this machine, and the sign-in
// is a POST with CSRF.
if (app()->isLocal()) {
    Route::get('dev/entrar', [DemoLoginController::class, 'index'])->name('dev.entrar');
    Route::post('dev/entrar/{user}', [DemoLoginController::class, 'store'])
        ->whereNumber('user')
        ->name('dev.entrar.usuario');
}
