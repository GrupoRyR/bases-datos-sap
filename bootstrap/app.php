<?php

use Illuminate\Database\QueryException;
use Illuminate\Foundation\Application;
use Illuminate\Foundation\Configuration\Exceptions;
use Illuminate\Foundation\Configuration\Middleware;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;

return Application::configure(basePath: dirname(__DIR__))
    ->withRouting(
        web: __DIR__.'/../routes/web.php',
        commands: __DIR__.'/../routes/console.php',
        health: '/up',
    )
    ->withMiddleware(function (Middleware $middleware): void {
        // Core serves the Microsoft sign-in page and the home of the panel.
        $middleware->redirectGuestsTo(fn (): string => route('core.login'));
        $middleware->redirectUsersTo(fn (): string => route('core.inicio'));
    })
    ->withExceptions(function (Exceptions $exceptions): void {
        $exceptions->shouldRenderJsonWhen(
            fn (Request $request) => $request->is('api/*') || $request->expectsJson(),
        );

        // A failed query's message holds every bound value, and the driver
        // text can quote them too (MySQL's "Duplicate entry 'X'"). SAP rows
        // carry personal data, so the log gets only the SQL template and the
        // error codes; the default report, with message and trace, is skipped.
        $exceptions->report(function (QueryException $e): void {
            $previous = $e->getPrevious();
            $errorInfo = $e->errorInfo ?? ($previous instanceof PDOException ? $previous->errorInfo : null);

            Log::error('database.query_failed', [
                'connection' => $e->getConnectionName(),
                'sqlstate' => $errorInfo[0] ?? null,
                'driver_code' => $errorInfo[1] ?? null,
                'sql' => $e->getSql(),
                'exception_class' => $e::class,
            ]);
        })->stop();
    })->create();
