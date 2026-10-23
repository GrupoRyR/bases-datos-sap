<?php

use App\Support\Modules\Module;
use App\Support\Modules\ModuleServiceProvider;
use App\Support\Navigation\NavRegistry;
use Illuminate\Console\Scheduling\Event;
use Illuminate\Console\Scheduling\Schedule;
use Illuminate\Support\Facades\Route;
use Tests\Fixtures\Modules\Demo\Providers\DemoServiceProvider;

beforeEach(function () {
    $this->app->register(DemoServiceProvider::class);

    // The app is already booted, so name lookups must be rebuilt by hand
    // (Laravel does it once after boot for providers registered on time).
    Route::getRoutes()->refreshNameLookups();

    $this->moduleRoot = realpath(base_path('tests/Fixtures/Modules/Demo'));
});

it('derives the module from where its provider lives', function () {
    $provider = $this->app->getProvider(DemoServiceProvider::class);

    $module = (fn (): Module => $this->module())->call($provider);

    expect($module->name)->toBe('Demo')
        ->and($module->key())->toBe('demo')
        ->and($module->namespace)->toBe('Tests\Fixtures\Modules\Demo')
        ->and($module->path)->toBe($this->moduleRoot);
});

it('loads web routes under the module prefix and route name', function () {
    $route = Route::getRoutes()->getByName('demo.ping');

    expect($route)->not->toBeNull()
        ->and($route->uri())->toBe('demo/ping')
        ->and($route->gatherMiddleware())->toContain('web');

    $this->get('/demo/ping')->assertOk()->assertSee('pong');
});

it('loads api routes under api/<prefix> with the module api route name', function () {
    $route = Route::getRoutes()->getByName('demo.api.status');

    expect($route)->not->toBeNull()
        ->and($route->uri())->toBe('api/demo/status')
        ->and($route->gatherMiddleware())->toContain('api');

    // Answers only if the "api" middleware group exists.
    $this->getJson('/api/demo/status')->assertOk()->assertExactJson(['status' => 'ok']);
});

it('registers views and translations under the module key', function () {
    expect(view('demo::hello')->render())->toContain('Hola desde el módulo de prueba')
        ->and(__('demo::mensajes.saludo'))->toBe('Hola desde el módulo de prueba');
});

it('merges the module config under its key', function () {
    expect(config('demo.per_page'))->toBe(25);
});

it('registers the module migrations with the migrator', function () {
    expect(app('migrator')->paths())
        ->toContain($this->moduleRoot.DIRECTORY_SEPARATOR.'database'.DIRECTORY_SEPARATOR.'migrations');
});

it('adds the module tasks to the schedule', function () {
    $commands = array_map(fn (Event $event): string => (string) $event->command, app(Schedule::class)->events());

    expect(collect($commands)->contains(fn (string $command): bool => str_contains($command, 'demo:refresh')))->toBeTrue();
});

it('adds the module entries to the navigation', function () {
    expect(app(NavRegistry::class)->has('demo.inicio'))->toBeTrue();
});

it('keeps register and boot final so modules only extend the hooks', function () {
    expect((new ReflectionMethod(ModuleServiceProvider::class, 'register'))->isFinal())->toBeTrue()
        ->and((new ReflectionMethod(ModuleServiceProvider::class, 'boot'))->isFinal())->toBeTrue();
});
