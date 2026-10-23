<?php

namespace Tests\Fixtures\Modules\Demo\Providers;

use App\Support\Modules\ModuleServiceProvider;
use App\Support\Navigation\NavItem;
use App\Support\Navigation\NavRegistry;
use Illuminate\Console\Scheduling\Schedule;

/**
 * Fixture module used by the module loader tests. It mirrors the layout of
 * app/Modules/<Module> and uses the default prefixes (/demo, demo.*).
 */
final class DemoServiceProvider extends ModuleServiceProvider
{
    protected function schedule(Schedule $schedule): void
    {
        $schedule->command('demo:refresh')->dailyAt('06:00');
    }

    protected function navigation(NavRegistry $navigation): void
    {
        $navigation->add(new NavItem(
            key: 'demo.inicio',
            label: 'Inicio de prueba',
            route: 'demo.ping',
            icon: 'home',
            group: 'Prueba',
            mobile: true,
        ));
    }
}
