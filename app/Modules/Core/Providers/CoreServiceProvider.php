<?php

namespace App\Modules\Core\Providers;

use App\Models\User;
use App\Modules\Core\Application\Auth\IdentityProvider;
use App\Modules\Core\Console\SetRoleCommand;
use App\Modules\Core\Contracts\AuditLogger;
use App\Modules\Core\Contracts\Enums\Role;
use App\Modules\Core\Http\Middleware\EnsureUserIsActive;
use App\Modules\Core\Infrastructure\Audit\DatabaseAuditLogger;
use App\Modules\Core\Infrastructure\Auth\SocialiteMicrosoftIdentityProvider;
use App\Support\Modules\ModuleServiceProvider;
use Illuminate\Contracts\Http\Kernel as HttpKernel;
use Illuminate\Foundation\Http\Kernel as FoundationHttpKernel;
use Illuminate\Support\Facades\Event;
use Illuminate\Support\Facades\Gate;
use Laravel\Socialite\Contracts\Factory as SocialiteFactory;
use RuntimeException;
use SocialiteProviders\Manager\SocialiteWasCalled;
use SocialiteProviders\Microsoft\Provider as MicrosoftProvider;

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

        // Microsoft Entra ID sign-in; tests bind a fake instead.
        $this->app->bind(IdentityProvider::class, SocialiteMicrosoftIdentityProvider::class);
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

        $this->registerMicrosoftDriver();
    }

    /**
     * The "microsoft" Socialite driver (config/services.php), for the
     * configured tenant only. Same creator as $event->extendSocialite(), plus
     * a fail-closed guard: without a tenant the driver falls back to "common"
     * and accepts accounts from any directory. It runs only when the driver
     * is built, so a missing tenant never breaks boot or /up, only sign-in.
     */
    private function registerMicrosoftDriver(): void
    {
        Event::listen(function (SocialiteWasCalled $event): void {
            // The singleton behind the Socialite facade (a SocialiteManager).
            $socialite = $this->app->make(SocialiteFactory::class);

            $socialite->extend('microsoft', function () use ($event, $socialite) {
                if (blank(config('services.microsoft.tenant'))) {
                    throw new RuntimeException(
                        'MICROSOFT_TENANT_ID is required: without it Microsoft sign-in would accept accounts from any directory ("common").',
                    );
                }

                return $event->buildProvider($socialite, 'microsoft', MicrosoftProvider::class, null);
            });
        });
    }
}
