<?php

use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

// One MySQL database per purpose (plan §3): the app's own data, then one per
// dataset, so each consumer app can be granted only the databases it reads.
dataset('connections', [
    'app' => ['app', 'DB_DATABASE'],
    'maestros' => ['maestros', 'DB_MAESTROS_DATABASE'],
    'cartera' => ['cartera', 'DB_CARTERA_DATABASE'],
]);

it('uses the app connection by default', function () {
    expect(config('database.default'))->toBe('app');
});

it('builds every connection with the same supported driver', function () {
    $drivers = collect(['app', 'maestros', 'cartera'])
        ->map(fn (string $name): mixed => config("database.connections.{$name}.driver"));

    expect($drivers->unique()->values()->all())->toHaveCount(1)
        ->and($drivers->first())->toBeIn(['mysql', 'sqlite']);
});

it('answers a query on the connection', function (string $name) {
    $row = DB::connection($name)->selectOne('select 1 as ok');

    expect((int) $row->ok)->toBe(1);
})->with('connections');

it('points the connection at its own database', function (string $name, string $variable) {
    expect(DB::connection($name)->getDatabaseName())->toBe(env($variable));
})->with('connections');

it('keeps every connection on a different MySQL database', function () {
    $databases = collect(['app', 'maestros', 'cartera'])
        ->map(fn (string $name): string => DB::connection($name)->getDatabaseName());

    expect($databases->unique())->toHaveCount(3);
})->skip(fn (): bool => env('DB_DRIVER', 'mysql') !== 'mysql', 'Only MySQL has separate databases; SQLite tests use one in-memory database per connection.');

it('wraps every connection in the test transaction once any of them is used', function (string $name) {
    DB::connection($name)->select('select 1');

    foreach (['app', 'maestros', 'cartera'] as $connection) {
        expect(DB::connection($connection)->transactionLevel())->toBe(1);
    }
})->with('connections');

it('creates the tables of a migration on the connection it names', function () {
    $migration = base_path('tests/Fixtures/Modules/Demo/database/migrations/2026_11_09_000000_create_demo_catalogo_table.php');

    expect(Schema::connection('maestros')->hasTable('demo_catalogo'))->toBeFalse();

    $this->artisan('migrate', ['--path' => $migration, '--realpath' => true])->assertSuccessful();

    expect(Schema::connection('maestros')->hasTable('demo_catalogo'))->toBeTrue()
        ->and(Schema::connection('app')->hasTable('demo_catalogo'))->toBeFalse()
        ->and(Schema::connection('cartera')->hasTable('demo_catalogo'))->toBeFalse();

    $this->artisan('migrate:rollback', ['--path' => $migration, '--realpath' => true])->assertSuccessful();

    expect(Schema::connection('maestros')->hasTable('demo_catalogo'))->toBeFalse();
});
