<?php

use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Domain\Runs\RunState;
use App\Modules\Sap\Models\Run;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Testing\TestResponse;
use Tests\Modules\Sap\Support\RobotClient;
use Tests\TestCase;

/*
| A kilos run (docs/contrato-robot.md, section 10.5): one VENTAS month before
| the nightly window, like a historical one, whose batches bring only the key,
| the posting date and the weight. Its close writes only kilos on the lines
| already stored, and only when the lines match MySQL exactly; anything else
| fails without touching a line.
*/

beforeEach(function () {
    RobotClient::configure();
    // On 16/10 the nightly window starts on 24/09.
    Carbon::setTestNow(Carbon::parse('2026-10-16 10:00:00', 'America/Bogota'));
});

/**
 * The start body of a kilos run of SGX for August 2026.
 *
 * @param  array<string, mixed>  $overrides
 * @return array<string, mixed>
 */
function kilosRun(array $overrides = []): array
{
    return array_merge([
        'conjunto' => 'VENTAS',
        'empresa' => 'SGX',
        'tipo' => 'kilos',
        'partes' => ['ventas' => 'todo'],
        'solicitudes' => [],
        'fecha_corte' => null,
        'ventana_desde' => '2026-08-01',
        'ventana_hasta' => '2026-08-31',
        'extraida_en' => '2026-10-16T09:58:00-05:00',
    ], $overrides);
}

/**
 * A VENTAS line already stored, without kilos.
 *
 * @return array<string, mixed>
 */
function kilosStoredLine(string $company, int $entry, string $postedOn, int $line = 0): array
{
    return [
        ...RobotClient::row(Part::Sales, [
            'tipo_objeto' => 13, 'doc_entry' => $entry, 'linea' => $line,
            'fecha_contabilizacion' => $postedOn, 'fecha_documento' => $postedOn, 'total' => "{$entry}00.00",
        ]),
        'empresa' => $company,
        'sincronizado_en' => '2026-10-01 02:30:00',
        'corrida_id' => 7,
    ];
}

/**
 * One line of a kilos batch, by column name.
 *
 * @return array<string, mixed>
 */
function kilosLine(int $entry, string $postedOn, ?string $kilos, int $line = 0): array
{
    return ['tipo_objeto' => 13, 'doc_entry' => $entry, 'linea' => $line, 'fecha_contabilizacion' => $postedOn, 'kilos' => $kilos];
}

/**
 * A kilos batch body with the given header, by default the reduced one.
 *
 * @param  list<array<string, mixed>>  $lines
 * @param  list<string>  $columns
 * @return array<string, mixed>
 */
function kilosBatch(int $number, array $lines, array $columns = ['tipo_objeto', 'doc_entry', 'linea', 'fecha_contabilizacion', 'kilos']): array
{
    return [
        'batch' => $number,
        'parte' => 'ventas',
        'columns' => $columns,
        'rows' => array_map(fn (array $line): array => array_map(fn (string $column): mixed => $line[$column] ?? null, $columns), $lines),
    ];
}

/**
 * Opens a kilos run, sends the lines in one batch and returns the run id.
 *
 * @param  list<array<string, mixed>>  $lines
 * @param  array<string, mixed>  $overrides
 */
function sendKilos(TestCase $test, array $lines, array $overrides = []): int
{
    $run = (int) RobotClient::post($test, '/api/robot/v1/corridas', kilosRun($overrides))->assertCreated()->json('run_id');
    RobotClient::post($test, "/api/robot/v1/corridas/{$run}/lotes", kilosBatch(1, $lines))->assertCreated();

    return $run;
}

function closeKilos(TestCase $test, int $run, int $rows, ?int $sap = null): TestResponse
{
    return RobotClient::post($test, "/api/robot/v1/corridas/{$run}/cerrar", [
        'batches' => 1, 'filas' => ['ventas' => $rows], 'conteo_sap' => ['ventas' => $sap ?? $rows],
    ]);
}

/** @return list<array<string, mixed>> Every stored line with all its columns, sorted by company and key. */
function kilosSnapshot(): array
{
    return DB::connection('ventas')->table('ventas')->orderBy('empresa')->orderBy('doc_entry')->orderBy('linea')->get()
        ->map(fn (object $row): array => (array) $row)->all();
}

/** @return array<string, float|null> The kilos of every stored line by "<empresa>/<doc_entry>/<linea>". */
function storedKilos(): array
{
    return DB::connection('ventas')->table('ventas')->orderBy('empresa')->orderBy('doc_entry')->orderBy('linea')->get()
        ->mapWithKeys(fn (object $row): array => ["{$row->empresa}/{$row->doc_entry}/{$row->linea}" => $row->kilos === null ? null : (float) $row->kilos])
        ->all();
}

/** @return array<string, mixed> The month the tests load: SGX lines in and around August and an SDC line with a SGX key. */
function kilosMonth(): array
{
    return [
        kilosStoredLine('SGX', 1, '2026-08-01'),
        kilosStoredLine('SGX', 1, '2026-08-01', 1),
        kilosStoredLine('SGX', 2, '2026-08-31'),
        // Outside the range: neither filled nor missing.
        kilosStoredLine('SGX', 9, '2026-07-31'),
        kilosStoredLine('SGX', 10, '2026-09-24'),
        // Another company's line with the same key as an SGX one.
        kilosStoredLine('SDC', 1, '2026-08-01'),
    ];
}

it('fills only the kilos of the company lines of the month and touches nothing else', function () {
    DB::connection('ventas')->table('ventas')->insert(kilosMonth());
    $before = kilosSnapshot();

    $run = sendKilos($this, [
        kilosLine(1, '2026-08-01', '12.500000'),
        kilosLine(1, '2026-08-01', '-3.250000', 1),
        kilosLine(2, '2026-08-31', '0.000000'),
    ]);

    closeKilos($this, $run, 3)
        ->assertOk()
        ->assertJsonPath('estado', 'cerrada')
        ->assertJsonPath('conteo.ventas', ['sap' => 3, 'recibidas' => 3, 'activas_recibidas' => 3, 'activas_mysql' => 3, 'cuadra' => true]);

    $withoutKilos = fn (array $rows): array => array_map(fn (array $row): array => array_diff_key($row, ['kilos' => true]), $rows);

    expect(storedKilos())->toBe([
        'SDC/1/0' => null,
        'SGX/1/0' => 12.5,
        'SGX/1/1' => -3.25,
        'SGX/2/0' => 0.0,
        'SGX/9/0' => null,
        'SGX/10/0' => null,
    ])
        // Every other column, sincronizado_en and corrida_id included, stays as it was.
        ->and($withoutKilos(kilosSnapshot()))->toBe($withoutKilos($before))
        ->and(Run::find($run)->tipo->value)->toBe('kilos')
        // A kilos load never stands for the nightly count of the day.
        ->and(DB::table('daily_counts')->count())->toBe(0);
});

it('rewrites the same kilos when the month runs again, with no 409', function () {
    DB::connection('ventas')->table('ventas')->insert(kilosMonth());
    $lines = [kilosLine(1, '2026-08-01', '12.500000'), kilosLine(1, '2026-08-01', '-3.250000', 1), kilosLine(2, '2026-08-31', '4.000000')];

    closeKilos($this, sendKilos($this, $lines), 3)->assertOk();
    $first = kilosSnapshot();

    closeKilos($this, sendKilos($this, $lines), 3)->assertOk();

    expect(kilosSnapshot())->toBe($first)
        ->and(storedKilos()['SGX/2/0'])->toBe(4.0);
});

it('fails the close and changes nothing when a line is not stored for the company in the range', function () {
    DB::connection('ventas')->table('ventas')->insert(kilosMonth());
    $before = kilosSnapshot();

    // Line 9 is stored but in July; line 3 is not stored at all.
    $run = sendKilos($this, [
        kilosLine(1, '2026-08-01', '1.000000'), kilosLine(1, '2026-08-01', '1.000000', 1), kilosLine(2, '2026-08-31', '1.000000'),
        kilosLine(3, '2026-08-15', '1.000000'),
    ]);

    closeKilos($this, $run, 4)
        ->assertUnprocessable()
        ->assertJsonPath('sobran', 1)
        ->assertJsonPath('faltan', 0)
        ->assertJsonValidationErrorFor('filas.ventas');

    expect(kilosSnapshot())->toBe($before)
        ->and(Run::find($run)->estado)->toBe(RunState::Failed);
});

it('does not take a line of another company as stored', function () {
    DB::connection('ventas')->table('ventas')->insert([kilosStoredLine('SDC', 1, '2026-08-01')]);

    $run = sendKilos($this, [kilosLine(1, '2026-08-01', '1.000000')]);

    closeKilos($this, $run, 1)->assertUnprocessable()->assertJsonPath('sobran', 1)->assertJsonPath('faltan', 0);

    expect(storedKilos())->toBe(['SDC/1/0' => null]);
});

it('fails the close and changes nothing when a stored line of the range did not arrive', function () {
    DB::connection('ventas')->table('ventas')->insert(kilosMonth());
    $before = kilosSnapshot();

    $run = sendKilos($this, [kilosLine(1, '2026-08-01', '1.000000'), kilosLine(2, '2026-08-31', '1.000000')]);

    closeKilos($this, $run, 2)
        ->assertUnprocessable()
        ->assertJsonPath('sobran', 0)
        ->assertJsonPath('faltan', 1)
        ->assertJsonValidationErrorFor('filas.ventas');

    expect(kilosSnapshot())->toBe($before)
        ->and(Run::find($run)->estado)->toBe(RunState::Failed)
        ->and(Run::find($run)->error)->toContain('sobran 0')->toContain('faltan 1');
});

it('fails the close and changes nothing when the SAP count differs from the lines received', function () {
    DB::connection('ventas')->table('ventas')->insert(kilosMonth());
    $before = kilosSnapshot();

    $run = sendKilos($this, [kilosLine(1, '2026-08-01', '1.000000'), kilosLine(1, '2026-08-01', '1.000000', 1), kilosLine(2, '2026-08-31', '1.000000')]);

    closeKilos($this, $run, 3, sap: 4)
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('conteo_sap.ventas');

    expect(kilosSnapshot())->toBe($before)
        ->and(Run::find($run)->estado)->toBe(RunState::Failed);
});

it('requires the SAP count to close a kilos run', function () {
    DB::connection('ventas')->table('ventas')->insert(kilosMonth());
    $run = sendKilos($this, [kilosLine(1, '2026-08-01', '1.000000')]);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['ventas' => 1]])
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('conteo_sap');
});

it('opens a kilos run on a range that already has lines', function () {
    DB::connection('ventas')->table('ventas')->insert(kilosMonth());

    RobotClient::post($this, '/api/robot/v1/corridas', kilosRun())->assertCreated();

    expect(Run::sole()->ventana_hasta?->toDateString())->toBe('2026-08-31');
});

it('accepts January 2025 and the days of the month before the nightly window', function (array $range) {
    RobotClient::post($this, '/api/robot/v1/corridas', kilosRun($range))->assertCreated();
})->with([
    'January 2025' => [['ventana_desde' => '2025-01-01', 'ventana_hasta' => '2025-01-31']],
    'up to the day before the nightly window' => [['ventana_desde' => '2026-09-01', 'ventana_hasta' => '2026-09-23']],
]);

it('refuses a kilos range that is not within one month before the nightly window', function (array $range, string $field) {
    RobotClient::post($this, '/api/robot/v1/corridas', kilosRun($range))
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor($field);

    expect(Run::count())->toBe(0);
})->with([
    'reaching the nightly window' => [['ventana_desde' => '2026-09-01', 'ventana_hasta' => '2026-09-24'], 'ventana_hasta'],
    'crossing into the next month' => [['ventana_hasta' => '2026-09-01'], 'ventana_hasta'],
    'before 2025-01-01' => [['ventana_desde' => '2024-12-01', 'ventana_hasta' => '2024-12-31'], 'ventana_desde'],
    'not the first day of a month' => [['ventana_desde' => '2026-08-02'], 'ventana_desde'],
    'without ventana_hasta' => [['ventana_hasta' => null], 'ventana_hasta'],
    'serving requests' => [['solicitudes' => [1]], 'solicitudes'],
]);

it('refuses a kilos run of any other dataset', function (string $dataset) {
    RobotClient::post($this, '/api/robot/v1/corridas', kilosRun(['conjunto' => $dataset, 'partes' => ['pedidos' => 'todo']]))
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('tipo');
})->with(['MAESTROS', 'CARTERA', 'PEDIDOS', 'PRODUCCION']);

it('takes only the reduced header in a kilos batch', function (array $columns) {
    $run = (int) RobotClient::post($this, '/api/robot/v1/corridas', kilosRun())->assertCreated()->json('run_id');
    $line = RobotClient::row(Part::Sales, ['doc_entry' => 1, 'fecha_contabilizacion' => '2026-08-01', 'fecha_documento' => '2026-08-01', 'kilos' => '1.000000']);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", kilosBatch(1, [$line], $columns))
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('columns');
})->with([
    'the full sales header' => [array_keys(Part::Sales->columns())],
    'without kilos' => [['tipo_objeto', 'doc_entry', 'linea', 'fecha_contabilizacion']],
    'with another sales column' => [['tipo_objeto', 'doc_entry', 'linea', 'fecha_contabilizacion', 'kilos', 'total']],
]);

it('takes the reduced header in any order, a line without kilos, and refuses a line outside the range', function () {
    $run = (int) RobotClient::post($this, '/api/robot/v1/corridas', kilosRun())->assertCreated()->json('run_id');
    $columns = ['kilos', 'linea', 'fecha_contabilizacion', 'doc_entry', 'tipo_objeto'];

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", kilosBatch(1, [
        kilosLine(1, '2026-08-01', null), kilosLine(2, '2026-07-31', '1.000000'), kilosLine(3, '2026-08-15', '1.000000'),
    ], $columns))
        ->assertUnprocessable()
        ->assertJsonValidationErrors(['rows.1.fecha_contabilizacion'])
        ->assertJsonMissingValidationErrors(['rows.0.kilos', 'rows.0.fecha_contabilizacion', 'rows.2.fecha_contabilizacion']);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", kilosBatch(1, [
        kilosLine(2, '2026-07-31', '1.000000'), kilosLine(3, '2026-09-01', '1.000000'), kilosLine(4, '2026-08-15', '1.000000'),
    ], $columns))
        ->assertUnprocessable()
        ->assertJsonValidationErrors(['rows.0.fecha_contabilizacion', 'rows.1.fecha_contabilizacion'])
        ->assertJsonMissingValidationErrors(['rows.2.fecha_contabilizacion']);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", kilosBatch(1, [kilosLine(4, '2026-08-15', '1.000000'), kilosLine(5, '2026-08-16', null)], $columns))
        ->assertCreated();
});

it('refuses a key repeated across the batches of a kilos run', function () {
    $run = (int) RobotClient::post($this, '/api/robot/v1/corridas', kilosRun())->assertCreated()->json('run_id');

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", kilosBatch(1, [kilosLine(1, '2026-08-01', '1.000000')]))->assertCreated();
    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", kilosBatch(2, [kilosLine(1, '2026-08-01', '2.000000')]))
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('rows.0.tipo_objeto');
});
