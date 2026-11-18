<?php

use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Domain\Runs\RunState;
use App\Modules\Sap\Models\Run;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Tests\Modules\Sap\Support\RobotClient;
use Tests\TestCase;

/*
| A PEDIDOS run (docs/contrato-robot.md, sections 4 and 11): the open lines
| of customer orders, a photo of what is open when the robot extracts it.
| It has no cut-off date and no window, and its close replaces every order
| line of the company. An empty close fails and keeps the previous lines.
*/

beforeEach(function () {
    RobotClient::configure();
    Carbon::setTestNow(Carbon::parse('2026-11-17 10:00:00', 'America/Bogota'));
});

/**
 * The start body of a PEDIDOS run of SGX.
 *
 * @param  array<string, mixed>  $overrides
 * @return array<string, mixed>
 */
function pedidosRun(array $overrides = []): array
{
    return array_merge([
        'conjunto' => 'PEDIDOS',
        'empresa' => 'SGX',
        'tipo' => 'solicitud',
        'partes' => ['pedidos' => 'todo'],
        'solicitudes' => [],
        'fecha_corte' => null,
        'extraida_en' => '2026-11-17T09:58:00-05:00',
    ], $overrides);
}

/**
 * An open order line as the robot sends it.
 *
 * @param  array<string, mixed>  $overrides
 * @return array<string, mixed>
 */
function orderLine(int $entry, int $line = 0, array $overrides = []): array
{
    return RobotClient::row(Part::Orders, ['doc_entry' => $entry, 'linea' => $line, ...$overrides]);
}

/**
 * An order line already in ventas_sap.
 *
 * @return array<string, mixed>
 */
function storedOrder(string $company, int $entry, string $total = '100.00'): array
{
    return [
        ...orderLine($entry, 0, ['total_pendiente' => $total]),
        'empresa' => $company,
        'sincronizado_en' => '2026-11-16 02:30:00',
    ];
}

/**
 * Opens a PEDIDOS run, sends the lines in one batch and returns the run id.
 *
 * @param  list<array<string, mixed>>  $lines
 * @param  array<string, mixed>  $overrides
 */
function sendPedidos(TestCase $test, array $lines, array $overrides = []): int
{
    $run = (int) RobotClient::post($test, '/api/robot/v1/corridas', pedidosRun($overrides))->assertCreated()->json('run_id');

    if ($lines !== []) {
        RobotClient::post($test, "/api/robot/v1/corridas/{$run}/lotes", RobotClient::batch(1, Part::Orders, $lines))->assertCreated();
    }

    return $run;
}

/** @return list<string> "<empresa>/<doc_entry>-<linea>/<total_pendiente>" of every stored line, sorted. */
function storedOrders(): array
{
    return DB::connection('ventas')->table('pedidos')->orderBy('empresa')->orderBy('doc_entry')->orderBy('linea')->get()
        ->map(fn (object $row): string => "{$row->empresa}/{$row->doc_entry}-{$row->linea}/".number_format((float) $row->total_pendiente, 2, '.', ''))
        ->all();
}

it('opens a PEDIDOS run without cut-off date or window', function () {
    RobotClient::post($this, '/api/robot/v1/corridas', pedidosRun())->assertCreated();

    $run = Run::sole();

    expect($run->fecha_corte)->toBeNull()
        ->and($run->ventana_desde)->toBeNull()
        ->and($run->partes)->toBe(['pedidos' => 'todo']);
});

it('refuses a PEDIDOS run with a cut-off date, a window, in changes or without its part', function (array $overrides, string $field) {
    RobotClient::post($this, '/api/robot/v1/corridas', pedidosRun($overrides))
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor($field);

    expect(Run::count())->toBe(0);
})->with([
    'cut-off date' => [['fecha_corte' => '2026-11-16'], 'fecha_corte'],
    'window' => [['ventana_desde' => '2026-10-25'], 'ventana_desde'],
    'in changes' => [['partes' => ['pedidos' => 'cambios']], 'partes.pedidos'],
    'a part of another dataset' => [['partes' => ['ventas' => 'todo']], 'partes.ventas'],
    'full run without its part' => [['tipo' => 'completa', 'partes' => []], 'partes'],
]);

it('accepts each of the four ranges of the contract', function (string $range) {
    $run = sendPedidos($this, []);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", RobotClient::batch(1, Part::Orders, [orderLine(1, 0, ['rango' => $range])]))
        ->assertCreated();
})->with(['Hasta 30 dias', 'De 31 a 60 dias', 'De 61 a 90 dias', 'Mas de 90 dias']);

it('refuses a line key repeated in the run, inside a batch or across batches', function () {
    $run = sendPedidos($this, [orderLine(1), orderLine(1, 1)]);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", RobotClient::batch(2, Part::Orders, [
        orderLine(2),
        orderLine(1, 1),
        orderLine(2),
    ]))->assertUnprocessable()
        ->assertJsonValidationErrors(['rows.1.doc_entry', 'rows.2.doc_entry'])
        ->assertJsonMissingValidationErrors(['rows.0.doc_entry']);
});

it('refuses a line without a required column or with a value of the wrong type', function (array $overrides, string $field) {
    $run = sendPedidos($this, []);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", RobotClient::batch(1, Part::Orders, [orderLine(1, 0, $overrides)]))
        ->assertUnprocessable()
        ->assertJsonValidationErrors(["rows.0.{$field}"]);

    expect(DB::table('robot_batches')->count())->toBe(0);
})->with([
    'no range' => [['rango' => null], 'rango'],
    'range with an accent' => [['rango' => 'Hasta 30 días'], 'rango'],
    'range outside the four of the contract' => [['rango' => 'Mas de 120 dias'], 'rango'],
    'no item' => [['codigo_articulo' => ''], 'codigo_articulo'],
    'no pending total' => [['total_pendiente' => null], 'total_pendiente'],
    'pending quantity with 7 decimals' => [['cantidad_pendiente' => '1.1234567'], 'cantidad_pendiente'],
    'amount with 3 decimals' => [['ganancia_bruta_pendiente' => '10.505'], 'ganancia_bruta_pendiente'],
    'days late as text' => [['dias_atraso' => '-3'], 'dias_atraso'],
    'impossible commitment date' => [['fecha_compromiso' => '2026-02-30'], 'fecha_compromiso'],
]);

it('replaces every order line of the company and leaves the other company and VENTAS alone', function () {
    DB::connection('ventas')->table('pedidos')->insert([
        // Invoiced or closed since the last run: gone with the replacement.
        storedOrder('SGX', 1, '111.00'),
        // Still open: replaced by what arrives.
        storedOrder('SGX', 2, '222.00'),
        // The other company: untouched.
        storedOrder('SDC', 2, '333.00'),
    ]);
    DB::connection('ventas')->table('ventas')->insert([
        ...RobotClient::row(Part::Sales, ['fecha_contabilizacion' => '2026-11-10', 'fecha_documento' => '2026-11-10']),
        'empresa' => 'SGX', 'sincronizado_en' => '2026-11-16 02:30:00',
    ]);

    $run = sendPedidos($this, [
        orderLine(2, 0, ['total_pendiente' => '200.50', 'dias_atraso' => -4, 'cantidad_pendiente' => '400.000000']),
        orderLine(3, 0, ['total_pendiente' => '0.00']),
        orderLine(3, 1, ['total_pendiente' => '555.00']),
    ]);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['pedidos' => 3]])
        ->assertOk()
        ->assertJsonPath('estado', 'cerrada');

    $line = (array) DB::connection('ventas')->table('pedidos')->where('empresa', 'SGX')->where('doc_entry', 2)->sole();

    expect(storedOrders())->toBe(['SDC/2-0/333.00', 'SGX/2-0/200.50', 'SGX/3-0/0.00', 'SGX/3-1/555.00'])
        ->and((int) $line['dias_atraso'])->toBe(-4)
        ->and((float) $line['cantidad_pendiente'])->toBe(400.0)
        ->and($line['sincronizado_en'])->toStartWith('2026-11-17 10:00:00')
        ->and((int) $line['corrida_id'])->toBe($run)
        ->and(DB::connection('ventas')->table('ventas')->count())->toBe(1)
        ->and(DB::connection('ventas')->table('pedidos')->where('empresa', 'SDC')->value('sincronizado_en'))->toStartWith('2026-11-16 02:30:00');
});

it('fails an empty close and keeps the previous order lines', function () {
    DB::connection('ventas')->table('pedidos')->insert(storedOrder('SGX', 7));
    $run = sendPedidos($this, []);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 0, 'filas' => ['pedidos' => 0]])
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('filas.pedidos');

    expect(Run::find($run)->estado)->toBe(RunState::Failed)
        ->and(storedOrders())->toBe(['SGX/7-0/100.00']);
});

it('counts every order line of the company in the nightly run', function () {
    DB::connection('ventas')->table('pedidos')->insert([storedOrder('SGX', 1), storedOrder('SDC', 2)]);
    $run = sendPedidos($this, [orderLine(3), orderLine(3, 1), orderLine(4)], ['tipo' => 'completa']);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['pedidos' => 3], 'conteo_sap' => ['pedidos' => 3]])
        ->assertOk()
        ->assertJsonPath('conteo.pedidos', ['sap' => 3, 'recibidas' => 3, 'activas_recibidas' => 3, 'activas_mysql' => 3, 'cuadra' => true]);

    $count = DB::table('daily_counts')->sole();

    expect($count->conjunto)->toBe('PEDIDOS')
        ->and($count->parte)->toBe('pedidos')
        ->and($count->empresa)->toBe('SGX')
        ->and($count->fecha)->toStartWith('2026-11-17');
});

it('records a nightly count that does not match SAP without failing the run', function () {
    $run = sendPedidos($this, [orderLine(1), orderLine(2)], ['tipo' => 'completa']);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['pedidos' => 2], 'conteo_sap' => ['pedidos' => 5]])
        ->assertOk()
        ->assertJsonPath('estado', 'cerrada')
        ->assertJsonPath('conteo.pedidos.cuadra', false);

    expect((bool) DB::table('daily_counts')->value('cuadra'))->toBeFalse();
});
