<?php

use App\Modules\Sap\Models\RobotComparison;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Testing\TestResponse;
use Tests\Modules\Sap\Support\RobotClient;
use Tests\TestCase;

/*
| POST /api/robot/v1/comparaciones (docs/contrato-robot.md, section 13.3):
| the robot reports how its totals of SAP compared with those of MySQL. It
| is stored for the coordinator and the panel, never applied to the data.
*/

const COMPARISON_PATH = '/api/robot/v1/comparaciones';

beforeEach(function () {
    RobotClient::configure();
    Carbon::setTestNow(Carbon::parse('2026-11-27 03:10:00', 'America/Bogota'));
});

/**
 * @param  array<string, mixed>  $overrides
 * @return array<string, mixed>
 */
function comparisonBody(array $overrides = []): array
{
    return array_merge([
        'conjunto' => 'VENTAS',
        'empresa' => 'SGX',
        'comparada_en' => '2026-11-27T03:05:00-05:00',
        'desde' => '2025-01-01',
        'hasta' => '2026-11-26',
        'cuadra' => false,
        'diferencias' => [
            ['clave' => '2026-10', 'campo' => 'filas', 'sap' => '1204', 'mysql' => '1203'],
            ['clave' => '2026-10', 'campo' => 'sumas.total', 'sap' => '1000.50', 'mysql' => null],
        ],
    ], $overrides);
}

/** @param  array<string, mixed>  $body */
function compare(TestCase $test, array $body): TestResponse
{
    return RobotClient::post($test, COMPARISON_PATH, $body);
}

it('stores the comparison and answers its id', function () {
    $id = compare($this, comparisonBody())->assertCreated()->json('id');

    $stored = RobotComparison::findOrFail($id);

    expect($id)->toBeInt()
        ->and($stored->conjunto->value)->toBe('VENTAS')
        ->and($stored->empresa->value)->toBe('SGX')
        ->and($stored->desde?->toDateString())->toBe('2025-01-01')
        ->and($stored->hasta?->toDateString())->toBe('2026-11-26')
        ->and($stored->cuadra)->toBeFalse()
        ->and($stored->diferencias)->toBe(comparisonBody()['diferencias'])
        ->and($stored->comparada_en->toIso8601String())->toBe('2026-11-27T03:05:00-05:00')
        ->and($stored->robot_key)->toBe(RobotClient::KEY)
        ->and($stored->created_at->equalTo(now()))->toBeTrue();
});

it('stores a comparison that matches, without range outside VENTAS', function (string $dataset) {
    $id = compare($this, comparisonBody(['conjunto' => $dataset, 'empresa' => 'SDC', 'desde' => null, 'hasta' => null, 'cuadra' => true, 'diferencias' => []]))
        ->assertCreated()
        ->json('id');

    $stored = RobotComparison::findOrFail($id);

    expect($stored->cuadra)->toBeTrue()
        ->and($stored->diferencias)->toBe([])
        ->and($stored->desde)->toBeNull()
        ->and($stored->hasta)->toBeNull();
})->with(['MAESTROS', 'CARTERA', 'VENTAS']);

it('keeps the time in Bogota whatever zone the robot sent', function () {
    $id = compare($this, comparisonBody(['comparada_en' => '2026-11-27T08:05:00Z']))->assertCreated()->json('id');

    expect(RobotComparison::findOrFail($id)->comparada_en->toIso8601String())->toBe('2026-11-27T03:05:00-05:00');
});

it('accepts up to 500 differences', function () {
    $differences = array_fill(0, 500, ['clave' => '2026-10', 'campo' => 'nulos.kilos', 'sap' => '0', 'mysql' => '3']);

    compare($this, comparisonBody(['diferencias' => $differences]))->assertCreated();

    expect(RobotComparison::sole()->diferencias)->toHaveCount(500);
});

it('answers the first id and stores nothing new when the robot repeats a comparison', function () {
    $first = compare($this, comparisonBody())->assertCreated()->json('id');

    // The robot lost the answer and sends the same comparison again.
    $again = compare($this, comparisonBody(['cuadra' => true, 'diferencias' => []]))->assertCreated()->json('id');

    expect($again)->toBe($first)
        ->and(RobotComparison::count())->toBe(1)
        ->and(RobotComparison::findOrFail($first)->cuadra)->toBeFalse();
});

it('stores another comparison for another time, company or dataset', function (array $overrides) {
    compare($this, comparisonBody())->assertCreated();
    compare($this, comparisonBody($overrides))->assertCreated();

    expect(RobotComparison::count())->toBe(2);
})->with([
    'another time' => [['comparada_en' => '2026-11-27T03:06:00-05:00']],
    'another company' => [['empresa' => 'SDC']],
    'another dataset' => [['conjunto' => 'CARTERA', 'desde' => null, 'hasta' => null]],
]);

it('refuses a comparison made in the future, beyond five minutes of clock drift', function (string $comparedAt, bool $stored) {
    $response = compare($this, comparisonBody(['comparada_en' => $comparedAt]));

    $stored ? $response->assertCreated() : $response->assertUnprocessable()->assertJsonValidationErrorFor('comparada_en');

    expect(RobotComparison::count())->toBe($stored ? 1 : 0);
})->with([
    // The server clock reads 03:10 in Bogota.
    'five minutes ahead' => ['2026-11-27T03:15:00-05:00', true],
    'more than five minutes ahead' => ['2026-11-27T03:15:01-05:00', false],
    'a day ahead' => ['2026-11-28T03:10:00-05:00', false],
]);

it('writes nothing but the comparison', function () {
    $before = [
        'ventas' => DB::connection('ventas')->table('ventas')->count(),
        'robot_runs' => DB::table('robot_runs')->count(),
        'update_requests' => DB::table('update_requests')->count(),
    ];

    compare($this, comparisonBody())->assertCreated();

    expect([
        'ventas' => DB::connection('ventas')->table('ventas')->count(),
        'robot_runs' => DB::table('robot_runs')->count(),
        'update_requests' => DB::table('update_requests')->count(),
    ])->toBe($before)->and(RobotComparison::count())->toBe(1);
});

it('refuses what the contract does not allow with 422 and stores nothing', function (array $overrides, string $field) {
    compare($this, comparisonBody($overrides))->assertUnprocessable()
        ->assertJsonPath('message', 'La comparación no cumple el contrato.')
        ->assertJsonStructure(['errors' => [$field]]);

    expect(RobotComparison::count())->toBe(0);
})->with([
    'unknown dataset' => [['conjunto' => 'COMPRAS'], 'conjunto'],
    'PEDIDOS' => [['conjunto' => 'PEDIDOS'], 'conjunto'],
    'PRODUCCION' => [['conjunto' => 'PRODUCCION'], 'conjunto'],
    'unknown company' => [['empresa' => 'sgx'], 'empresa'],
    'range on CARTERA' => [['conjunto' => 'CARTERA'], 'desde'],
    'until on MAESTROS' => [['conjunto' => 'MAESTROS', 'desde' => null], 'hasta'],
    'bad from' => [['desde' => '2025-13-01'], 'desde'],
    'from after until' => [['desde' => '2026-11-27', 'hasta' => '2026-11-26'], 'hasta'],
    'no time' => [['comparada_en' => null], 'comparada_en'],
    'time without zone' => [['comparada_en' => '2026-11-27T03:05:00'], 'comparada_en'],
    'a date for a time' => [['comparada_en' => '2026-11-27'], 'comparada_en'],
    'no cuadra' => [['cuadra' => null], 'cuadra'],
    'cuadra as text' => [['cuadra' => 'false'], 'cuadra'],
    'cuadra as number' => [['cuadra' => 0], 'cuadra'],
    'no differences' => [['diferencias' => null], 'diferencias'],
    'differences as object' => [['diferencias' => ['a' => ['clave' => 'x', 'campo' => 'filas', 'sap' => '1', 'mysql' => '2']]], 'diferencias'],
    'matches with differences' => [['cuadra' => true], 'diferencias'],
    'does not match without differences' => [['cuadra' => false, 'diferencias' => []], 'diferencias'],
    'over 500 differences' => [['diferencias' => array_fill(0, 501, ['clave' => '2026-10', 'campo' => 'filas', 'sap' => '1', 'mysql' => '2'])], 'diferencias'],
    'a difference that is not an object' => [['diferencias' => ['filas']], 'diferencias.0'],
    'no key' => [['diferencias' => [['campo' => 'filas', 'sap' => '1', 'mysql' => '2']]], 'diferencias.0.clave'],
    'empty key' => [['diferencias' => [['clave' => '', 'campo' => 'filas', 'sap' => '1', 'mysql' => '2']]], 'diferencias.0.clave'],
    'key over 20' => [['diferencias' => [['clave' => str_repeat('k', 21), 'campo' => 'filas', 'sap' => '1', 'mysql' => '2']]], 'diferencias.0.clave'],
    'numeric key' => [['diferencias' => [['clave' => 202610, 'campo' => 'filas', 'sap' => '1', 'mysql' => '2']]], 'diferencias.0.clave'],
    'field over 40' => [['diferencias' => [['clave' => '2026-10', 'campo' => str_repeat('c', 41), 'sap' => '1', 'mysql' => '2']]], 'diferencias.0.campo'],
    'no field' => [['diferencias' => [['clave' => '2026-10', 'sap' => '1', 'mysql' => '2']]], 'diferencias.0.campo'],
    'numeric sap value' => [['diferencias' => [['clave' => '2026-10', 'campo' => 'filas', 'sap' => 1, 'mysql' => '2']]], 'diferencias.0.sap'],
    'mysql value over 40' => [['diferencias' => [['clave' => '2026-10', 'campo' => 'filas', 'sap' => '1', 'mysql' => str_repeat('9', 41)]]], 'diferencias.0.mysql'],
    'missing mysql value' => [['diferencias' => [['clave' => '2026-10', 'campo' => 'filas', 'sap' => '1']]], 'diferencias.0.mysql'],
    'extra key' => [['diferencias' => [['clave' => '2026-10', 'campo' => 'filas', 'sap' => '1', 'mysql' => '2', 'nota' => 'x']]], 'diferencias.0'],
]);

it('refuses an unsigned request with the usual 401 and stores nothing', function () {
    RobotClient::post($this, COMPARISON_PATH, comparisonBody(), headers: ['X-Robot-Key' => null])
        ->assertUnauthorized()
        ->assertExactJson(['message' => 'Firma inválida.']);

    expect(RobotComparison::count())->toBe(0);
});

it('reads the differences back in contract key order, whatever order the database keeps', function () {
    $id = compare($this, comparisonBody())->assertCreated()->json('id');

    // MySQL's JSON type sorts object keys (by length, then alphabetically).
    DB::table('robot_comparisons')->where('id', $id)->update(['diferencias' => json_encode([
        ['sap' => '1204', 'clave' => '2026-10', 'campo' => 'filas', 'mysql' => '1203'],
        ['sap' => '1000.50', 'clave' => '2026-10', 'campo' => 'sumas.total', 'mysql' => null],
    ])]);

    expect(RobotComparison::findOrFail($id)->diferencias)->toBe(comparisonBody()['diferencias']);
});
