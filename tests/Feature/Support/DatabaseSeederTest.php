<?php

use App\Support\Modules\ModuleRegistry;
use Database\Seeders\DatabaseSeeder;
use Illuminate\Support\Facades\Cache;

beforeEach(function () {
    // Seed from the fixture modules instead of app/Modules.
    $this->app->instance(
        ModuleRegistry::class,
        new ModuleRegistry(base_path('tests/Fixtures/Modules'), 'Tests\Fixtures\Modules'),
    );
});

it('runs the database seeder of every module', function () {
    $this->seed(DatabaseSeeder::class);

    expect(Cache::get('demo.seeders.database'))->toBe(1);
});

it('skips the module demo seeders outside the local environment', function () {
    $this->seed(DatabaseSeeder::class);

    expect(Cache::get('demo.seeders.demo'))->toBeNull();
});

it('runs the module demo seeders in the local environment', function () {
    $this->app['env'] = 'local';

    $this->seed(DatabaseSeeder::class);

    expect(Cache::get('demo.seeders.database'))->toBe(1)
        ->and(Cache::get('demo.seeders.demo'))->toBe(1);
});
