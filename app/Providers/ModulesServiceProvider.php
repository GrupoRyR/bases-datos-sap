<?php

namespace App\Providers;

use App\Support\Modules\ModuleRegistry;
use Illuminate\Support\ServiceProvider;

/**
 * Registers the service provider of every module under app/Modules, Core
 * first (docs/arquitectura.md). Nobody edits
 * bootstrap/providers.php to add a module.
 */
class ModulesServiceProvider extends ServiceProvider
{
    public function register(): void
    {
        $modules = new ModuleRegistry(app_path('Modules'));

        $this->app->instance(ModuleRegistry::class, $modules);

        foreach ($modules->all() as $module) {
            if (class_exists($module->providerClass())) {
                $this->app->register($module->providerClass());
            }
        }
    }
}
