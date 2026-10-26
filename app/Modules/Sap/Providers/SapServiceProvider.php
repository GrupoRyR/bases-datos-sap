<?php

namespace App\Modules\Sap\Providers;

use App\Modules\Sap\Console\ExpireCommand;
use App\Modules\Sap\Http\Middleware\DecodeRobotBody;
use App\Modules\Sap\Http\Middleware\LimitRobotPayload;
use App\Modules\Sap\Http\Middleware\VerifyRobotSignature;
use App\Modules\Sap\Infrastructure\Robot\NonceStore;
use App\Support\Modules\ModuleServiceProvider;
use Illuminate\Cache\RateLimiting\Limit;
use Illuminate\Console\Scheduling\Schedule;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\RateLimiter;
use Illuminate\Support\Facades\Route;

/**
 * Sap: the MAESTROS and CARTERA data, the robot ingest (runs and batches),
 * update requests and the API the apps call (docs/plan-bases-sap.md,
 * sections 2 and 4). Owner: the «Datos y API» session.
 *
 * Web routes: /sap/*, named sap.*.
 * API routes: /api/robot/v1/* and /api/v1/* exactly as the robot contract
 * says (empty apiPrefix()), named sap.api.*.
 * Migrations: 2026_11_02_*. It may use only Core contracts.
 */
final class SapServiceProvider extends ModuleServiceProvider
{
    /**
     * The contract fixes the paths, so the API is served directly under /api.
     */
    protected function apiPrefix(): string
    {
        return '';
    }

    protected function bootModule(): void
    {
        $this->commands([ExpireCommand::class]);

        // Every robot route, in this order: rate limit, size, signature, body.
        Route::middlewareGroup('sap.robot', [
            'throttle:sap-robot',
            LimitRobotPayload::class,
            VerifyRobotSignature::class,
            DecodeRobotBody::class,
        ]);

        RateLimiter::for('sap-robot', fn (Request $request) => Limit::perMinute((int) config('sap.robot.requests_per_minute'))
            ->by('sap-robot|'.$request->ip())
            ->response(fn (Request $request, array $headers) => response()->json(['message' => 'Demasiadas peticiones.'], 429, $headers)));
    }

    protected function schedule(Schedule $schedule): void
    {
        $schedule->command('sap:vencer')->everyMinute()->withoutOverlapping();

        $schedule->call(fn () => app(NonceStore::class)->prune())
            ->name('sap:limpiar-nonces')
            ->everyTenMinutes()
            ->withoutOverlapping();
    }
}
