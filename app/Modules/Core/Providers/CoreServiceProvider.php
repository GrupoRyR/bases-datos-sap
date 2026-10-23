<?php

namespace App\Modules\Core\Providers;

use App\Models\User;
use App\Modules\Core\Console\SetRoleCommand;
use App\Modules\Core\Contracts\AuditLogger;
use App\Modules\Core\Contracts\Enums\Role;
use App\Modules\Core\Http\Middleware\EnsureUserIsActive;
use App\Modules\Core\Infrastructure\Audit\DatabaseAuditLogger;
use App\Support\Modules\ModuleServiceProvider;
use Illuminate\Contracts\Http\Kernel as HttpKernel;
use Illuminate\Foundation\Http\Kernel as FoundationHttpKernel;
use Illuminate\Support\Facades\Gate;

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

    protected function registerModule(): void
    {
        // Reads the signed-in user and the request, so one per request (or job).
        $this->app->scoped(AuditLogger::class, DatabaseAuditLogger::class);
    }

    protected function bootModule(): void
    {
        // Sap and Panel check access by these names (Core README).
        Gate::define('core.consultar', fn (User $user): bool => $user->is_active && $user->role !== null);
        Gate::define('core.administrar', fn (User $user): bool => $user->is_active && $user->hasRole(Role::AdminTi));

        $this->commands([SetRoleCommand::class]);

        // Every web page signs out a deactivated user, with or without auth.
        // Appended through the HTTP kernel, not only the router: resolving the
        // kernel after boot (as tests do) syncs its groups into the router and
        // would drop a router-only push.
        $this->callAfterResolving(HttpKernel::class, function (HttpKernel $kernel): void {
            if ($kernel instanceof FoundationHttpKernel) {
                $kernel->appendMiddlewareToGroup('web', EnsureUserIsActive::class);
            }
        });
    }
}
