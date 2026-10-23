<?php

use App\Support\Modules\Module;
use App\Support\Modules\ModuleRegistry;
use App\Support\Modules\ModuleServiceProvider;

/*
|--------------------------------------------------------------------------
| Module boundaries (docs/arquitectura.md)
|--------------------------------------------------------------------------
|
| A module uses another module only through that module's Contracts
| namespace, and only if $mayUse below allows it. The registry is built
| when this file loads (the app is not booted yet), so one set of rules is
| generated per module found under app/Modules.
|
*/

$contracts = fn (string $module): string => "App\\Modules\\{$module}\\Contracts";

// The modules whose contracts each module may use. Panel reads Sap data.
$mayUse = [
    'Core' => [],
    'Sap' => ['Core'],
    'Panel' => ['Core', 'Sap'],
];

$modules = (new ModuleRegistry(__DIR__.'/../../app/Modules'))->all();

foreach ($modules as $module) {
    $others = array_values(array_map(
        fn (Module $other): string => $other->namespace,
        array_filter($modules, fn (Module $other): bool => $other->name !== $module->name),
    ));

    $allowed = array_map($contracts, $mayUse[$module->name] ?? []);

    it("declares which modules {$module->name} may use", function () use ($mayUse, $module) {
        expect($mayUse)->toHaveKey($module->name);
    });

    if ($others !== []) {
        // ignoring() drops the uses whose name starts with an allowed
        // Contracts namespace, so only those contracts stay reachable.
        arch("{$module->name} reaches other modules only through the contracts it may use")
            ->expect($module->namespace)
            ->not->toUse($others)
            ->ignoring($allowed);
    }

    it("registers {$module->name} through a final ModuleServiceProvider", function () use ($module) {
        expect(class_exists($module->providerClass()))->toBeTrue()
            ->and(is_subclass_of($module->providerClass(), ModuleServiceProvider::class))->toBeTrue()
            ->and((new ReflectionClass($module->providerClass()))->isFinal())->toBeTrue();
    });

    it("keeps {$module->name} migrations on its reserved date prefix", function () use ($module) {
        $prefix = config("modules.migration_prefixes.{$module->name}");

        expect($prefix)->toBeString();

        foreach (glob($module->path('database/migrations').DIRECTORY_SEPARATOR.'*.php') ?: [] as $migration) {
            expect(basename($migration))->toStartWith($prefix.'_');
        }
    });
}

arch('shared support code does not depend on modules except Core contracts')
    ->expect('App\\Support')
    ->not->toUse('App\\Modules')
    ->ignoring($contracts('Core'));

arch('application code ships without debugging helpers')
    ->expect('App')
    ->not->toUse(['dd', 'dump', 'ray', 'var_dump', 'die']);
