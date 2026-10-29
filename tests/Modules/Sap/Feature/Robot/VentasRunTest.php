<?php

use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Models\Run;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Tests\Modules\Sap\Support\RobotClient;
use Tests\TestCase;

/*
| A VENTAS run (docs/contrato-robot.md, sections 4 and 10): it starts with
| the first day of its window, and its batches never bring a line before
| that day.
*/

beforeEach(function () {
    RobotClient::configure();
    // On 16/10 the query's window starts on 24/09.
    Carbon::setTestNow(Carbon::parse('2026-10-16 10:00:00', 'America/Bogota'));
});

/**
 * The start body of a VENTAS run of SGX with its window.
 *
 * @param  array<string, mixed>  $overrides
 * @return array<string, mixed>
 */
function ventasRun(array $overrides = []): array
{
    return array_merge([
        'conjunto' => 'VENTAS',
        'empresa' => 'SGX',
        'tipo' => 'solicitud',
        'partes' => ['ventas' => 'todo'],
        'solicitudes' => [],
        'fecha_corte' => null,
        'ventana_desde' => '2026-09-24',
        'extraida_en' => '2026-10-16T09:58:00-05:00',
    ], $overrides);
}

/**
 * A sale line as the robot sends it.
 *
 * @param  array<string, mixed>  $overrides
 * @return array<string, mixed>
 */
function saleLine(int $entry, string $postedOn, array $overrides = []): array
{
    return RobotClient::row(Part::Sales, [
        'tipo_objeto' => 13, 'doc_entry' => $entry, 'linea' => 0,
        'fecha_contabilizacion' => $postedOn, 'fecha_documento' => $postedOn, ...$overrides,
    ]);
}

/**
 * Opens a VENTAS run, sends the lines in one batch and returns the run id.
 *
 * @param  list<array<string, mixed>>  $lines
 * @param  array<string, mixed>  $overrides
 */
function sendVentas(TestCase $test, array $lines, array $overrides = []): int
{
    $run = (int) RobotClient::post($test, '/api/robot/v1/corridas', ventasRun($overrides))->assertCreated()->json('run_id');

    if ($lines !== []) {
        RobotClient::post($test, "/api/robot/v1/corridas/{$run}/lotes", RobotClient::batch(1, Part::Sales, $lines))->assertCreated();
    }

    return $run;
}

it('opens a VENTAS run and keeps the first day of its window', function () {
    RobotClient::post($this, '/api/robot/v1/corridas', ventasRun())->assertCreated();

    $run = Run::sole();

    expect($run->ventana_desde?->toDateString())->toBe('2026-09-24')
        ->and($run->fecha_corte)->toBeNull()
        ->and($run->partes)->toBe(['ventas' => 'todo']);
});

it('accepts a window from today minus 40 days to tomorrow', function (string $from) {
    RobotClient::post($this, '/api/robot/v1/corridas', ventasRun(['ventana_desde' => $from]))->assertCreated();
})->with(['2026-09-06', '2026-10-17']);

it('refuses a VENTAS run without a valid window, with a cut-off date or in changes', function (array $overrides, string $field) {
    RobotClient::post($this, '/api/robot/v1/corridas', ventasRun($overrides))
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor($field);

    expect(Run::count())->toBe(0);
})->with([
    'without window' => [['ventana_desde' => null], 'ventana_desde'],
    'window not a date' => [['ventana_desde' => '2026-9-24'], 'ventana_desde'],
    'impossible window' => [['ventana_desde' => '2026-02-30'], 'ventana_desde'],
    'window after tomorrow' => [['ventana_desde' => '2026-10-18'], 'ventana_desde'],
    'window before today minus 40 days' => [['ventana_desde' => '2026-09-05'], 'ventana_desde'],
    'cut-off date' => [['fecha_corte' => '2026-10-15'], 'fecha_corte'],
    'in changes' => [['partes' => ['ventas' => 'cambios']], 'partes.ventas'],
    'full run without its part' => [['tipo' => 'completa', 'partes' => []], 'partes'],
]);

it('counts the window from today in Bogota, not in UTC', function () {
    // 20:00 in Bogota is already the 17th in UTC: the 18th is still after tomorrow.
    Carbon::setTestNow(Carbon::parse('2026-10-16 20:00:00', 'America/Bogota'));

    RobotClient::post($this, '/api/robot/v1/corridas', ventasRun(['ventana_desde' => '2026-10-18']))
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('ventana_desde');
});

it('refuses a window in the other datasets', function (array $run) {
    RobotClient::post($this, '/api/robot/v1/corridas', [...$run, 'solicitudes' => [], 'ventana_desde' => '2026-09-24', 'extraida_en' => '2026-10-16T09:58:00-05:00'])
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('ventana_desde');
})->with([
    'MAESTROS' => [['conjunto' => 'MAESTROS', 'empresa' => 'SGX', 'tipo' => 'solicitud', 'partes' => ['marcas' => 'todo'], 'fecha_corte' => null]],
    'CARTERA' => [['conjunto' => 'CARTERA', 'empresa' => 'SGX', 'tipo' => 'solicitud', 'partes' => ['cartera' => 'todo'], 'fecha_corte' => '2026-10-16']],
]);

it('refuses a batch line posted before the window', function () {
    $run = sendVentas($this, []);
    $path = "/api/robot/v1/corridas/{$run}/lotes";

    RobotClient::post($this, $path, RobotClient::batch(1, Part::Sales, [saleLine(1, '2026-09-24'), saleLine(2, '2026-09-23')]))
        ->assertUnprocessable()
        ->assertJsonValidationErrors(['rows.1.fecha_contabilizacion'])
        ->assertJsonMissingValidationErrors(['rows.0.fecha_contabilizacion']);

    expect(Run::find($run)->lotes_rechazados)->toBe(1)
        ->and(Run::find($run)->isOpen())->toBeTrue()
        ->and(DB::table('robot_batches')->count())->toBe(0);
});

it('refuses a line key repeated in the run', function () {
    $run = sendVentas($this, [saleLine(1, '2026-10-01'), saleLine(1, '2026-10-01', ['linea' => 1])]);

    // A credit note may share DocEntry and line with an invoice; the same type, document and line may not repeat.
    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", RobotClient::batch(2, Part::Sales, [
        saleLine(1, '2026-10-01', ['tipo_objeto' => 14]),
        saleLine(1, '2026-10-02', ['linea' => 1]),
    ]))->assertUnprocessable()
        ->assertJsonValidationErrors(['rows.1.tipo_objeto'])
        ->assertJsonMissingValidationErrors(['rows.0.tipo_objeto']);
});
