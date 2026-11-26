<?php

use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Domain\Runs\RunState;
use App\Modules\Sap\Models\Run;
use Illuminate\Database\Events\QueryExecuted;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Tests\Modules\Sap\Support\RobotClient;
use Tests\TestCase;

/*
| A VENTAS run (docs/contrato-robot.md, sections 4 and 10): it starts with
| the first day of its window, its batches never bring a line before that
| day, and its close replaces only the company's window. Every earlier line
| is the frozen history Comisiones reads and is never touched.
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
 * A sale line already in ventas_sap.
 *
 * @return array<string, mixed>
 */
function storedSale(string $company, int $entry, string $postedOn, string $total = '100.00'): array
{
    return [
        ...saleLine($entry, $postedOn, ['total' => $total]),
        'empresa' => $company,
        'sincronizado_en' => '2026-10-01 02:30:00',
    ];
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

/** @return list<string> "<empresa>/<doc_entry>/<total>" of every stored line, sorted. */
function storedSales(): array
{
    return DB::connection('ventas')->table('ventas')->orderBy('empresa')->orderBy('doc_entry')->get()
        ->map(fn (object $row): string => "{$row->empresa}/{$row->doc_entry}/".number_format((float) $row->total, 2, '.', ''))
        ->all();
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

it('replaces only the window of the company and never touches earlier lines', function () {
    DB::connection('ventas')->table('ventas')->insert([
        // Before the window: frozen history, kept as it was.
        storedSale('SGX', 1, '2026-09-23', '111.00'),
        // Inside the window: replaced by what arrives, gone if it did not arrive.
        storedSale('SGX', 2, '2026-09-24', '222.00'),
        storedSale('SGX', 3, '2026-10-10', '333.00'),
        // The other company, inside the window: untouched.
        storedSale('SDC', 4, '2026-10-01', '444.00'),
    ]);

    $lines = [saleLine(2, '2026-09-24', ['total' => '-200.50', 'cantidad' => '-1.500000']), saleLine(5, '2026-10-15', ['total' => '555.00'])];
    $run = sendVentas($this, $lines);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['ventas' => 2]])
        ->assertOk()
        ->assertJsonPath('estado', 'cerrada');

    $line = (array) DB::connection('ventas')->table('ventas')->where('empresa', 'SGX')->where('doc_entry', 2)->sole();

    expect(storedSales())->toBe(['SDC/4/444.00', 'SGX/1/111.00', 'SGX/2/-200.50', 'SGX/5/555.00'])
        ->and((float) $line['cantidad'])->toBe(-1.5)
        ->and($line['sincronizado_en'])->toStartWith('2026-10-16 10:00:00')
        ->and((int) $line['corrida_id'])->toBe($run)
        ->and(DB::connection('ventas')->table('ventas')->where('doc_entry', 1)->value('sincronizado_en'))->toStartWith('2026-10-01 02:30:00');
});

/**
 * A batch body of sale lines whose header leaves out the given columns, as the
 * robot did before it sent ganancia_bruta.
 *
 * @param  list<array<string, mixed>>  $lines
 * @param  list<string>  $without
 * @return array<string, mixed>
 */
function ventasBatchWithout(array $lines, array $without): array
{
    $body = RobotClient::batch(1, Part::Sales, $lines);
    $keep = array_keys(array_filter($body['columns'], fn (string $column): bool => ! in_array($column, $without, true)));

    return [
        ...$body,
        'columns' => array_values(array_intersect_key($body['columns'], array_flip($keep))),
        'rows' => array_map(fn (array $row): array => array_values(array_intersect_key($row, array_flip($keep))), $body['rows']),
    ];
}

it('stores the gross profit of a line and keeps it negative on a credit note', function () {
    $run = sendVentas($this, [
        saleLine(1, '2026-10-01', ['total' => '1000.00', 'ganancia_bruta' => '250.75']),
        saleLine(2, '2026-10-02', ['tipo_objeto' => 14, 'total' => '-400.00', 'ganancia_bruta' => '-100.50']),
    ]);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['ventas' => 2]])->assertOk();

    $profit = DB::connection('ventas')->table('ventas')->orderBy('doc_entry')->pluck('ganancia_bruta', 'doc_entry')
        ->map(fn (mixed $value): float => (float) $value)->all();

    expect($profit)->toBe([1 => 250.75, 2 => -100.5]);
});

it('stores a null gross profit when the batch header leaves the column out', function () {
    $run = (int) RobotClient::post($this, '/api/robot/v1/corridas', ventasRun())->assertCreated()->json('run_id');

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", ventasBatchWithout([saleLine(1, '2026-10-01', ['total' => '1000.00'])], ['ganancia_bruta']))
        ->assertCreated()
        ->assertJson(['batch' => 1, 'rows' => 1]);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['ventas' => 1]])->assertOk();

    $line = (array) DB::connection('ventas')->table('ventas')->sole();

    expect($line['ganancia_bruta'])->toBeNull()
        ->and((float) $line['total'])->toBe(1000.0);
});

it('stores the kilos of a line, negative on a credit note, and null when the header leaves them out', function () {
    $run = sendVentas($this, [
        saleLine(1, '2026-10-01', ['kilos' => '25.125000']),
        saleLine(2, '2026-10-02', ['tipo_objeto' => 14, 'cantidad' => '-1.000000', 'kilos' => '-5.000000']),
    ], ['tipo' => 'completa']);
    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['ventas' => 2], 'conteo_sap' => ['ventas' => 2]])->assertOk();

    $kilos = fn (): array => DB::connection('ventas')->table('v_ventas')->orderBy('doc_entry')->pluck('kilos', 'doc_entry')
        ->map(fn (mixed $value): ?float => $value === null ? null : (float) $value)->all();

    expect($kilos())->toBe([1 => 25.125, 2 => -5.0]);

    $run = (int) RobotClient::post($this, '/api/robot/v1/corridas', ventasRun())->assertCreated()->json('run_id');
    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", ventasBatchWithout([saleLine(3, '2026-10-03')], ['kilos']))->assertCreated();
    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['ventas' => 1]])->assertOk();

    // The request run replaced the window with the one line it brought, without kilos.
    expect($kilos())->toBe([3 => null]);
});

it('stores the shipping code of a line, and null when the header leaves it out', function () {
    $run = sendVentas($this, [
        saleLine(1, '2026-10-01', ['codigo_envio' => '  CEDI BOGOTA  ']),
        saleLine(2, '2026-10-02', ['codigo_envio' => null]),
    ], ['tipo' => 'completa']);
    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['ventas' => 2], 'conteo_sap' => ['ventas' => 2]])->assertOk();

    $codes = fn (): array => DB::connection('ventas')->table('v_ventas')->orderBy('doc_entry')->pluck('codigo_envio', 'doc_entry')->all();

    expect($codes())->toBe([1 => 'CEDI BOGOTA', 2 => null]);

    $run = (int) RobotClient::post($this, '/api/robot/v1/corridas', ventasRun())->assertCreated()->json('run_id');
    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", ventasBatchWithout([saleLine(3, '2026-10-03')], ['codigo_envio', 'kilos']))->assertCreated();
    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['ventas' => 1]])->assertOk();

    expect($codes())->toBe([3 => null]);
});

it('still refuses a batch that misses or adds any other column', function (array $without, ?string $extra, string $message) {
    $run = (int) RobotClient::post($this, '/api/robot/v1/corridas', ventasRun())->assertCreated()->json('run_id');
    $body = ventasBatchWithout([saleLine(1, '2026-10-01')], $without);

    if ($extra !== null) {
        $body['columns'][] = $extra;
        $body['rows'][0][] = 'x';
    }

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", $body)
        ->assertUnprocessable()
        ->assertJsonPath('errors.columns.0', fn (string $found): bool => str_contains($found, $message));

    expect(DB::table('robot_batches')->count())->toBe(0);
})->with([
    'other column missing' => [['costo_total'], null, 'Faltan columnas: costo_total'],
    'other column missing next to the profit' => [['iva', 'ganancia_bruta'], null, 'Faltan columnas: iva'],
    'unknown column' => [['ganancia_bruta'], 'margen', 'Columnas desconocidas: margen'],
]);

it('refuses a gross profit that is not an amount', function () {
    $run = sendVentas($this, []);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", RobotClient::batch(1, Part::Sales, [saleLine(1, '2026-10-01', ['ganancia_bruta' => '10.505'])]))
        ->assertUnprocessable()
        ->assertJsonValidationErrors(['rows.0.ganancia_bruta']);
});

it('fails an empty close and keeps the previous window', function () {
    DB::connection('ventas')->table('ventas')->insert(storedSale('SGX', 3, '2026-10-10'));
    $run = sendVentas($this, []);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 0, 'filas' => ['ventas' => 0]])
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('filas.ventas');

    expect(Run::find($run)->estado)->toBe(RunState::Failed)
        ->and(storedSales())->toBe(['SGX/3/100.00']);
});

it('counts the lines of the company inside the window in the nightly run', function () {
    DB::connection('ventas')->table('ventas')->insert([
        storedSale('SGX', 1, '2026-09-01'),
        storedSale('SDC', 2, '2026-10-01'),
    ]);
    $run = sendVentas($this, [saleLine(3, '2026-09-24'), saleLine(4, '2026-10-15')], ['tipo' => 'completa']);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['ventas' => 2], 'conteo_sap' => ['ventas' => 2]])
        ->assertOk()
        ->assertJsonPath('conteo.ventas', ['sap' => 2, 'recibidas' => 2, 'activas_recibidas' => 2, 'activas_mysql' => 2, 'cuadra' => true]);

    $count = DB::table('daily_counts')->sole();

    expect($count->conjunto)->toBe('VENTAS')
        ->and($count->parte)->toBe('ventas')
        ->and($count->fecha)->toStartWith('2026-10-16');
});

/*
| A historical run (contract sections 4.1 and 10.4): one calendar month, or
| the part of it before the nightly window, loaded only into an empty range,
| all at once or not at all, so the frozen history is never touched.
*/

/**
 * The start body of a historical VENTAS run of SGX for August 2026.
 *
 * @param  array<string, mixed>  $overrides
 * @return array<string, mixed>
 */
function historicoRun(array $overrides = []): array
{
    return ventasRun(['tipo' => 'historico', 'ventana_desde' => '2026-08-01', 'ventana_hasta' => '2026-08-31', ...$overrides]);
}

it('loads a historical month into an empty range, with its SAP count and no daily count', function () {
    DB::connection('ventas')->table('ventas')->insert([
        storedSale('SGX', 1, '2026-07-31'),
        storedSale('SGX', 2, '2026-09-24'),
        // Another company's lines in the range do not block it.
        storedSale('SDC', 3, '2026-08-10'),
    ]);
    $run = sendVentas($this, [saleLine(4, '2026-08-01'), saleLine(5, '2026-08-31', ['total' => '-40.00'])], historicoRun());

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['ventas' => 2], 'conteo_sap' => ['ventas' => 2]])
        ->assertOk()
        ->assertJsonPath('estado', 'cerrada')
        ->assertJsonPath('conteo.ventas', ['sap' => 2, 'recibidas' => 2, 'activas_recibidas' => 2, 'activas_mysql' => 2, 'cuadra' => true]);

    $stored = Run::find($run);

    expect(storedSales())->toBe(['SDC/3/100.00', 'SGX/1/100.00', 'SGX/2/100.00', 'SGX/4/1000.50', 'SGX/5/-40.00'])
        ->and($stored->tipo->value)->toBe('historico')
        ->and($stored->ventana_hasta?->toDateString())->toBe('2026-08-31')
        // A historical load never stands for the nightly count of the day.
        ->and(DB::table('daily_counts')->count())->toBe(0);
});

it('accepts January 2025, the first month of the historical load', function () {
    RobotClient::post($this, '/api/robot/v1/corridas', historicoRun(['ventana_desde' => '2025-01-01', 'ventana_hasta' => '2025-01-31']))
        ->assertCreated();
});

it('accepts the days of the month before the nightly window starts', function () {
    // On 16/10 the nightly window starts on 24/09.
    RobotClient::post($this, '/api/robot/v1/corridas', historicoRun(['ventana_desde' => '2026-09-01', 'ventana_hasta' => '2026-09-23']))
        ->assertCreated();
});

it('refuses with 409 a range that already has lines of the company, and opens nothing', function () {
    DB::connection('ventas')->table('ventas')->insert(storedSale('SGX', 1, '2026-08-15'));

    RobotClient::post($this, '/api/robot/v1/corridas', historicoRun())->assertConflict();

    expect(Run::count())->toBe(0)
        ->and(storedSales())->toBe(['SGX/1/100.00']);
});

it('refuses a historical range that is not within one month before the nightly window', function (array $range, string $field) {
    RobotClient::post($this, '/api/robot/v1/corridas', historicoRun($range))
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor($field);

    expect(Run::count())->toBe(0);
})->with([
    'not the first day of a month' => [['ventana_desde' => '2026-08-02'], 'ventana_desde'],
    'before 2025-01-01' => [['ventana_desde' => '2024-12-01', 'ventana_hasta' => '2024-12-31'], 'ventana_desde'],
    'without ventana_desde' => [['ventana_desde' => null], 'ventana_desde'],
    'without ventana_hasta' => [['ventana_hasta' => null], 'ventana_hasta'],
    'ventana_hasta not a date' => [['ventana_hasta' => '2026-08-32'], 'ventana_hasta'],
    'crossing into the next month' => [['ventana_hasta' => '2026-09-01'], 'ventana_hasta'],
    'ending before it starts' => [['ventana_hasta' => '2026-07-31'], 'ventana_hasta'],
    'reaching the nightly window' => [['ventana_desde' => '2026-09-01', 'ventana_hasta' => '2026-09-24'], 'ventana_hasta'],
    'in the current month' => [['ventana_desde' => '2026-10-01', 'ventana_hasta' => '2026-10-15'], 'ventana_hasta'],
    'serving requests' => [['solicitudes' => [1]], 'solicitudes'],
]);

it('refuses a historical run of any other dataset', function (string $dataset) {
    RobotClient::post($this, '/api/robot/v1/corridas', historicoRun(['conjunto' => $dataset, 'partes' => ['pedidos' => 'todo']]))
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('tipo');
})->with(['MAESTROS', 'CARTERA', 'PEDIDOS', 'PRODUCCION']);

it('refuses ventana_hasta outside a historical run', function (string $type) {
    RobotClient::post($this, '/api/robot/v1/corridas', ventasRun(['tipo' => $type, 'ventana_hasta' => '2026-08-31']))
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('ventana_hasta');
})->with(['completa', 'solicitud']);

it('refuses a batch line outside the historical range', function () {
    $run = (int) RobotClient::post($this, '/api/robot/v1/corridas', historicoRun())->assertCreated()->json('run_id');

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", RobotClient::batch(1, Part::Sales, [
        saleLine(1, '2026-07-31'), saleLine(2, '2026-08-15'), saleLine(3, '2026-09-01'),
    ]))
        ->assertUnprocessable()
        ->assertJsonValidationErrors(['rows.0.fecha_contabilizacion', 'rows.2.fecha_contabilizacion'])
        ->assertJsonMissingValidationErrors(['rows.1.fecha_contabilizacion']);
});

it('requires the SAP count to close a historical run', function () {
    $run = sendVentas($this, [saleLine(1, '2026-08-15')], historicoRun());

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['ventas' => 1]])
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('conteo_sap');
});

it('fails a historical close whose SAP count differs from the lines received, and applies nothing', function () {
    $run = sendVentas($this, [saleLine(1, '2026-08-01'), saleLine(2, '2026-08-31')], historicoRun());

    // An applied month that does not match SAP could never be loaded again (409), so it is never applied.
    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['ventas' => 2], 'conteo_sap' => ['ventas' => 3]])
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('conteo_sap.ventas');

    expect(storedSales())->toBe([])
        ->and(Run::find($run)->estado)->toBe(RunState::Failed);
});

it('leaves the range empty when applying the historical month fails', function () {
    $lines = array_map(fn (int $entry): array => saleLine($entry, '2026-08-15'), range(1, 250));
    $run = (int) RobotClient::post($this, '/api/robot/v1/corridas', historicoRun())->assertCreated()->json('run_id');
    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", RobotClient::batch(1, Part::Sales, $lines))->assertCreated();

    // The second chunk of 200 lines fails after the first one was written.
    $inserts = 0;
    DB::listen(function (QueryExecuted $query) use (&$inserts) {
        if ($query->connectionName === 'ventas' && str_starts_with($query->sql, 'insert into') && str_contains($query->sql, 'ventas') && ++$inserts === 2) {
            throw new RuntimeException('Simulated failure while applying.');
        }
    });

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['ventas' => 250], 'conteo_sap' => ['ventas' => 250]])
        ->assertServerError();

    expect($inserts)->toBe(2)
        ->and(storedSales())->toBe([])
        ->and(Run::find($run)->estado)->toBe(RunState::Open);
});

it('keeps one open VENTAS run per company, historical or not', function () {
    RobotClient::post($this, '/api/robot/v1/corridas', historicoRun())->assertCreated();

    RobotClient::post($this, '/api/robot/v1/corridas', ventasRun(['tipo' => 'completa']))->assertConflict();
});
