<?php

use App\Modules\Core\Providers\CoreServiceProvider;
use App\Modules\Panel\Providers\PanelServiceProvider;
use App\Modules\Sap\Providers\SapServiceProvider;
use App\Support\Modules\ModuleRegistry;

it('discovers the three modules with Core first', function () {
    expect(app(ModuleRegistry::class)->names())->toBe(['Core', 'Panel', 'Sap']);
});

it('registers the service provider of every module', function () {
    foreach (app(ModuleRegistry::class)->all() as $module) {
        expect($this->app->getProvider($module->providerClass()))->not->toBeNull();
    }
});

it('serves Core at the site root and the other modules under their key', function () {
    $prefixes = fn (string $provider): array => (fn (): array => [$this->webPrefix(), $this->apiPrefix()])
        ->call($this->app->getProvider($provider));

    expect($prefixes(CoreServiceProvider::class))->toBe(['', 'core'])
        ->and($prefixes(SapServiceProvider::class))->toBe(['sap', 'sap'])
        ->and($prefixes(PanelServiceProvider::class))->toBe(['panel', 'panel']);
});

it('reserves a migration prefix for every module', function () {
    expect(config('modules.migration_prefixes'))->toBe([
        'Core' => '2026_11_01',
        'Sap' => '2026_11_02',
        'Panel' => '2026_11_03',
    ]);
});

it('seeds the database through the modules without errors', function () {
    expect(fn () => $this->seed())->not->toThrow(Throwable::class);
});
