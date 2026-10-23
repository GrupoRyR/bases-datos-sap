<?php

use Illuminate\Support\Facades\DB;

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

it('configures the connection', function (string $name) {
    expect(config("database.connections.{$name}"))->toBeArray()
        ->and(config("database.connections.{$name}.driver"))->toBe(env('DB_DRIVER', 'mysql'));
})->with('connections');

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
