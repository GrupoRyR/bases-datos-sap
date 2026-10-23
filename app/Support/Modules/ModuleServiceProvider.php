<?php

namespace App\Support\Modules;

use App\Support\Navigation\NavRegistry;
use Illuminate\Console\Scheduling\Schedule;
use Illuminate\Contracts\Foundation\CachesRoutes;
use Illuminate\Support\Facades\Route;
use Illuminate\Support\ServiceProvider;
use LogicException;
use ReflectionClass;

/**
 * Base provider of every module (docs/arquitectura.md).
 *
 * The module is derived from where the provider lives: the provider sits in
 * <module root>/Providers and its namespace is <module namespace>\Providers.
 * From there it loads, when present:
 *
 * - config/<key>.php, merged under the "<key>" config key;
 * - database/migrations;
 * - resources/views and resources/lang, under the "<key>::" namespace;
 * - routes/web.php: "web" middleware, /<webPrefix()>, names "<key>.*";
 * - routes/api.php: "api" middleware, /api/<apiPrefix()>, names "<key>.api.*".
 *
 * register() and boot() are final so every module loads the same way;
 * modules customize only the hooks below.
 */
abstract class ModuleServiceProvider extends ServiceProvider
{
    private ?Module $module = null;

    final public function register(): void
    {
        $config = $this->module()->path('config/'.$this->module()->key().'.php');

        if (is_file($config)) {
            $this->mergeConfigFrom($config, $this->module()->key());
        }

        $this->registerModule();
    }

    final public function boot(): void
    {
        $module = $this->module();

        if (is_dir($migrations = $module->path('database/migrations'))) {
            $this->loadMigrationsFrom($migrations);
        }

        if (is_dir($views = $module->path('resources/views'))) {
            $this->loadViewsFrom($views, $module->key());
        }

        if (is_dir($lang = $module->path('resources/lang'))) {
            $this->loadTranslationsFrom($lang, $module->key());
        }

        $this->loadModuleRoutes();

        $this->callAfterResolving(Schedule::class, function (Schedule $schedule): void {
            $this->schedule($schedule);
        });

        $this->callAfterResolving(NavRegistry::class, function (NavRegistry $navigation): void {
            $this->navigation($navigation);
        });

        $this->bootModule();
    }

    /**
     * Container bindings of the module, e.g. the implementation of a Core
     * contract. Runs inside register(), after the module config is merged.
     */
    protected function registerModule(): void
    {
        //
    }

    /**
     * Anything else the module needs once every provider is registered
     * (policies, event listeners, Blade components). Runs at the end of boot().
     */
    protected function bootModule(): void
    {
        //
    }

    /**
     * Scheduled tasks of the module (timezone America/Bogota). cPanel runs
     * "php artisan schedule:run" every minute.
     */
    protected function schedule(Schedule $schedule): void
    {
        //
    }

    /**
     * Sidebar and bottom-bar entries of the module.
     */
    protected function navigation(NavRegistry $navigation): void
    {
        //
    }

    /**
     * URL prefix of routes/web.php, without slashes. Empty serves the module
     * at the site root.
     */
    protected function webPrefix(): string
    {
        return $this->module()->key();
    }

    /**
     * URL prefix of routes/api.php after "api/", without slashes. Empty serves
     * the module API directly under /api.
     */
    protected function apiPrefix(): string
    {
        return $this->module()->key();
    }

    /**
     * The module this provider belongs to.
     */
    protected function module(): Module
    {
        return $this->module ??= $this->resolveModule();
    }

    private function resolveModule(): Module
    {
        $class = new ReflectionClass($this);
        $file = $class->getFileName();
        $separator = strrpos($class->getName(), '\\Providers\\');

        if ($file === false || $separator === false) {
            throw new LogicException("Module provider [{$class->getName()}] must live in <Module>/Providers under a <Module>\\Providers namespace.");
        }

        $root = dirname($file, 2);

        return new Module(
            name: basename($root),
            path: $root,
            namespace: substr($class->getName(), 0, $separator),
        );
    }

    private function loadModuleRoutes(): void
    {
        if ($this->app instanceof CachesRoutes && $this->app->routesAreCached()) {
            return;
        }

        $key = $this->module()->key();

        if (is_file($web = $this->module()->path('routes/web.php'))) {
            Route::middleware('web')
                ->prefix($this->webPrefix())
                ->name($key.'.')
                ->group($web);
        }

        if (is_file($api = $this->module()->path('routes/api.php'))) {
            Route::middleware('api')
                ->prefix(trim('api/'.$this->apiPrefix(), '/'))
                ->name($key.'.api.')
                ->group($api);
        }
    }
}
