<?php

use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\Part;
use Illuminate\Support\Facades\DB;
use Illuminate\Testing\TestResponse;
use Tests\Modules\Sap\Support\RobotClient;
use Tests\TestCase;

/*
| POST /api/robot/v1/totales (docs/contrato-robot.md, section 13.2): the
| totals the robot compares with SAP. Read only: rows, exact sums and null
| counts per month in VENTAS, the current receivables in CARTERA and the
| active rows per part in MAESTROS.
*/

const TOTALS_PATH = '/api/robot/v1/totales';

beforeEach(function () {
    RobotClient::configure();
});

/** @param  array<string, mixed>  $body */
function totals(TestCase $test, array $body): TestResponse
{
    return RobotClient::post($test, TOTALS_PATH, $body);
}

/**
 * A VENTAS line of a company with invented required columns.
 *
 * @param  array<string, mixed>  $overrides
 */
function totalsSale(string $date, string $total, string $quantity = '1.000000', array $overrides = []): void
{
    static $entry = 0;
    $entry++;

    DB::connection('ventas')->table('ventas')->insert(array_merge([
        'empresa' => 'SGX', 'tipo_objeto' => 13, 'doc_entry' => $entry, 'numero_documento' => $entry, 'linea' => 0,
        'clase_documento' => 'factura', 'estado_documento' => 'cerrado', 'fecha_documento' => $date,
        'fecha_contabilizacion' => $date, 'slp_code' => 1, 'codigo_cliente' => 'C1', 'cantidad' => $quantity,
        'total' => $total, 'kilos' => '1.000000', 'codigo_envio' => 'E1', 'sincronizado_en' => now(),
    ], $overrides));
}

function totalsReceivable(string $balance, string $company = 'SGX'): void
{
    DB::connection('cartera')->table('cartera')->insert([
        'empresa' => $company, 'codigo_sn' => 'C1', 'documento' => 'F1', 'fecha_vencimiento' => '2026-10-01',
        'dias' => 10, 'saldo' => $balance, 'sincronizado_en' => now(),
    ]);
}

function totalsMaster(string $table, string $code, bool $active = true, string $company = 'SGX'): void
{
    DB::connection('maestros')->table($table)->insert([
        'empresa' => $company, 'codigo' => $code, 'nombre' => "Fila {$code}", 'activo' => $active, 'sincronizado_en' => now(),
    ]);
}

it('groups VENTAS by posting month, ascending, with rows, exact sums and nulls', function () {
    totalsSale('2026-09-30', '1000.50', '2.500000');
    totalsSale('2026-10-01', '200.00', '1.000000', ['kilos' => null]);
    totalsSale('2026-10-31', '-50.25', '-0.500000', ['tipo_objeto' => 14, 'clase_documento' => 'nota_credito', 'codigo_envio' => null]);
    totalsSale('2026-08-15', '10.00', '1.000000', ['kilos' => null, 'codigo_envio' => null]);

    totals($this, ['conjunto' => 'VENTAS', 'empresa' => 'SGX'])->assertOk()->assertExactJson([
        'conjunto' => 'VENTAS',
        'empresa' => 'SGX',
        'grupos' => [
            ['clave' => '2026-08', 'filas' => 1, 'sumas' => ['total' => '10.00', 'cantidad' => '1.000000'], 'nulos' => ['kilos' => 1, 'codigo_envio' => 1]],
            ['clave' => '2026-09', 'filas' => 1, 'sumas' => ['total' => '1000.50', 'cantidad' => '2.500000'], 'nulos' => ['kilos' => 0, 'codigo_envio' => 0]],
            ['clave' => '2026-10', 'filas' => 2, 'sumas' => ['total' => '149.75', 'cantidad' => '0.500000'], 'nulos' => ['kilos' => 1, 'codigo_envio' => 1]],
        ],
    ]);
});

it('adds VENTAS amounts exactly, never as floats', function () {
    // 0.10 + 0.20 drifts as a float (0.30000000000000004); a thousand of them reach 300.00 only if exact.
    foreach (range(1, 500) as $i) {
        totalsSale('2026-10-05', '0.10', '0.100000');
        totalsSale('2026-10-06', '0.20', '0.000001');
    }
    totalsSale('2026-10-07', '12345678901.23', '1234567.123456');

    $group = totals($this, ['conjunto' => 'VENTAS', 'empresa' => 'SGX'])->assertOk()->json('grupos.0');

    expect($group['filas'])->toBe(1001)
        ->and($group['sumas'])->toBe(['total' => '12345679051.23', 'cantidad' => '1234617.123956']);
});

it('answers negative sums with a minus sign and exactly 2 and 6 decimals', function () {
    totalsSale('2026-10-05', '-12.5', '-3');

    expect(totals($this, ['conjunto' => 'VENTAS', 'empresa' => 'SGX'])->json('grupos.0.sumas'))
        ->toBe(['total' => '-12.50', 'cantidad' => '-3.000000']);
});

it('filters VENTAS by posting date, both ends included', function (array $range, array $months) {
    totalsSale('2026-09-30', '1.00');
    totalsSale('2026-10-01', '2.00');
    totalsSale('2026-10-31', '3.00');
    totalsSale('2026-11-01', '4.00');

    $groups = totals($this, ['conjunto' => 'VENTAS', 'empresa' => 'SGX', ...$range])->assertOk()->json('grupos');

    expect(array_map(fn (array $group): array => [$group['clave'], $group['sumas']['total']], $groups))->toBe($months);
})->with([
    'no range' => [[], [['2026-09', '1.00'], ['2026-10', '5.00'], ['2026-11', '4.00']]],
    'from only' => [['desde' => '2026-10-01'], [['2026-10', '5.00'], ['2026-11', '4.00']]],
    'until only' => [['hasta' => '2026-10-31'], [['2026-09', '1.00'], ['2026-10', '5.00']]],
    'one month' => [['desde' => '2026-10-01', 'hasta' => '2026-10-31'], [['2026-10', '5.00']]],
    'one day' => [['desde' => '2026-10-31', 'hasta' => '2026-10-31'], [['2026-10', '3.00']]],
    'nulls are no range' => [['desde' => null, 'hasta' => null], [['2026-09', '1.00'], ['2026-10', '5.00'], ['2026-11', '4.00']]],
]);

it('leaves out the other company and answers no groups when nothing matches', function () {
    totalsSale('2026-10-05', '9.99', '1.000000', ['empresa' => 'SDC']);

    totals($this, ['conjunto' => 'VENTAS', 'empresa' => 'SGX'])->assertOk()
        ->assertExactJson(['conjunto' => 'VENTAS', 'empresa' => 'SGX', 'grupos' => []]);

    expect(totals($this, ['conjunto' => 'VENTAS', 'empresa' => 'SDC'])->json('grupos.0.sumas.total'))->toBe('9.99');
});

it('totals the current CARTERA of the company in one group', function () {
    totalsReceivable('1000.10');
    totalsReceivable('-200.05');
    totalsReceivable('0.20');
    totalsReceivable('5.00', 'SDC');

    $response = totals($this, ['conjunto' => 'CARTERA', 'empresa' => 'SGX'])->assertOk()->assertExactJson([
        'conjunto' => 'CARTERA',
        'empresa' => 'SGX',
        'grupos' => [['clave' => 'actual', 'filas' => 3, 'sumas' => ['saldo' => '800.25'], 'nulos' => []]],
    ]);

    expect($response->getContent())->toContain('"nulos":{}');
});

it('answers an empty CARTERA with 0 rows and a 0.00 balance', function () {
    totals($this, ['conjunto' => 'CARTERA', 'empresa' => 'SDC'])->assertOk()->assertExactJson([
        'conjunto' => 'CARTERA',
        'empresa' => 'SDC',
        'grupos' => [['clave' => 'actual', 'filas' => 0, 'sumas' => ['saldo' => '0.00'], 'nulos' => []]],
    ]);
});

it('counts the active MAESTROS rows of the company per part, every part in order', function () {
    totalsMaster('clientes', 'C1');
    totalsMaster('clientes', 'C2');
    totalsMaster('clientes', 'C3', active: false);
    totalsMaster('clientes', 'C4', company: 'SDC');
    totalsMaster('marcas', '1');

    $response = totals($this, ['conjunto' => 'MAESTROS', 'empresa' => 'SGX'])->assertOk();
    $groups = $response->json('grupos');

    expect(array_column($groups, 'clave'))->toBe(array_map(fn (Part $part): string => $part->value, Part::forDataset(Dataset::Maestros)))
        ->and(array_column($groups, 'filas', 'clave'))->toMatchArray(['clientes' => 2, 'marcas' => 1, 'proveedores' => 0, 'municipios' => 0])
        ->and($response->getContent())->toContain('{"clave":"proveedores","filas":0,"sumas":{},"nulos":{}}');
});

it('changes nothing', function () {
    totalsSale('2026-10-05', '1.00');
    $before = DB::connection('ventas')->table('ventas')->get()->toArray();

    totals($this, ['conjunto' => 'VENTAS', 'empresa' => 'SGX'])->assertOk();

    expect(DB::connection('ventas')->table('ventas')->get()->toArray())->toEqual($before)
        ->and(DB::table('robot_comparisons')->count())->toBe(0);
});

it('refuses what the contract does not allow with 422', function (array $body, string $field) {
    totals($this, $body)->assertUnprocessable()
        ->assertJsonPath('message', 'La consulta no cumple el contrato.')
        ->assertJsonStructure(['errors' => [$field]]);
})->with([
    'unknown dataset' => [['conjunto' => 'COMPRAS', 'empresa' => 'SGX'], 'conjunto'],
    'no dataset' => [['empresa' => 'SGX'], 'conjunto'],
    'PEDIDOS' => [['conjunto' => 'PEDIDOS', 'empresa' => 'SGX'], 'conjunto'],
    'PRODUCCION' => [['conjunto' => 'PRODUCCION', 'empresa' => 'SGX'], 'conjunto'],
    'lowercase dataset' => [['conjunto' => 'ventas', 'empresa' => 'SGX'], 'conjunto'],
    'unknown company' => [['conjunto' => 'VENTAS', 'empresa' => 'XYZ'], 'empresa'],
    'no company' => [['conjunto' => 'VENTAS'], 'empresa'],
    'from on CARTERA' => [['conjunto' => 'CARTERA', 'empresa' => 'SGX', 'desde' => '2026-10-01'], 'desde'],
    'until on MAESTROS' => [['conjunto' => 'MAESTROS', 'empresa' => 'SGX', 'hasta' => '2026-10-01'], 'hasta'],
    'not a date' => [['conjunto' => 'VENTAS', 'empresa' => 'SGX', 'desde' => '2026-02-30'], 'desde'],
    'a time' => [['conjunto' => 'VENTAS', 'empresa' => 'SGX', 'hasta' => '2026-10-01T00:00:00-05:00'], 'hasta'],
    'a number' => [['conjunto' => 'VENTAS', 'empresa' => 'SGX', 'desde' => 20261001], 'desde'],
    'from after until' => [['conjunto' => 'VENTAS', 'empresa' => 'SGX', 'desde' => '2026-10-02', 'hasta' => '2026-10-01'], 'hasta'],
]);

it('refuses an unsigned request with the usual 401', function () {
    RobotClient::post($this, TOTALS_PATH, ['conjunto' => 'VENTAS', 'empresa' => 'SGX'], headers: ['X-Robot-Signature' => 'sha256='.str_repeat('a', 64)])
        ->assertUnauthorized()
        ->assertExactJson(['message' => 'Firma inválida.']);
});

it('reads a gzip body signed over the compressed bytes', function () {
    totalsReceivable('1.00');

    RobotClient::post($this, TOTALS_PATH, ['conjunto' => 'CARTERA', 'empresa' => 'SGX'], gzip: true)
        ->assertOk()
        ->assertJsonPath('grupos.0.filas', 1);
});
