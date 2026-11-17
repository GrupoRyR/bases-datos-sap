<?php

use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Domain\Runs\RunState;
use App\Modules\Sap\Models\Run;
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
        ->assertJsonPath('conteo.ventas', ['sap' => 2, 'recibidas' => 2, 'activas_mysql' => 2, 'cuadra' => true]);

    $count = DB::table('daily_counts')->sole();

    expect($count->conjunto)->toBe('VENTAS')
        ->and($count->parte)->toBe('ventas')
        ->and($count->fecha)->toStartWith('2026-10-16');
});
