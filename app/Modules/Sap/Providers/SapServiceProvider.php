<?php

namespace App\Modules\Sap\Providers;

use App\Modules\Sap\Application\Apps\AppKeys;
use App\Modules\Sap\Application\Panel\DatabaseDatasetStatuses;
use App\Modules\Sap\Application\Requests\PlaceRequest;
use App\Modules\Sap\Application\Requests\SettleRequests;
use App\Modules\Sap\Console\CreateAppKeyCommand;
use App\Modules\Sap\Console\ExpireCommand;
use App\Modules\Sap\Contracts\ClientAppKeys;
use App\Modules\Sap\Contracts\DatasetStatuses;
use App\Modules\Sap\Contracts\UpdateRequests;
use App\Modules\Sap\Domain\Runs\RunFinished;
use App\Modules\Sap\Http\Middleware\DecodeRobotBody;
use App\Modules\Sap\Http\Middleware\LimitRobotPayload;
use App\Modules\Sap\Http\Middleware\VerifyRobotSignature;
use App\Modules\Sap\Infrastructure\Robot\NonceStore;
use App\Support\Modules\ModuleServiceProvider;
use Illuminate\Cache\RateLimiting\Limit;
use Illuminate\Console\Scheduling\Schedule;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Event;
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

    protected function registerModule(): void
    {
        // The panel's "Actualizar datos" button asks through this contract.
        $this->app->bind(UpdateRequests::class, PlaceRequest::class);

        // The panel lists, creates, rotates and revokes app keys through this contract.
        $this->app->bind(ClientAppKeys::class, AppKeys::class);

        // What the TI panel reads.
        $this->app->bind(DatasetStatuses::class, DatabaseDatasetStatuses::class);
    }

    protected function bootModule(): void
    {
        $this->commands([ExpireCommand::class, CreateAppKeyCommand::class]);

        Event::listen(RunFinished::class, [SettleRequests::class, 'onRunFinished']);

        // The apps: per key, since apps on the same server share an IP; a
        // request without a key counts against its IP.
        RateLimiter::for('sap-apps', fn (Request $request) => Limit::perMinute((int) config('sap.apps.requests_per_minute'))
            ->by('sap-apps|'.(($token = $request->bearerToken()) ? hash('sha256', $token) : $request->ip()))
            ->response(fn (Request $request, array $headers) => response()->json(['message' => 'Demasiadas peticiones.'], 429, $headers)));

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
