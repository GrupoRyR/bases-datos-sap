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
| A complemento run (docs/contrato-robot.md, section 10.5): one VENTAS month
| before the nightly window, like a historical one, whose batches bring only
| the key, the posting date, the weight and the shipping code. Its close
| writes only kilos and codigo_envio on the lines already stored, and only
| when the lines match MySQL exactly; anything else fails without touching a
| line.
*/

beforeEach(function () {
    RobotClient::configure();
    // On 16/10 the nightly window starts on 24/09.
    Carbon::setTestNow(Carbon::parse('2026-10-16 10:00:00', 'America/Bogota'));
});

/** The reduced header of a complemento batch, in contract order. */
const COMPLEMENTO_COLUMNS = ['tipo_objeto', 'doc_entry', 'linea', 'fecha_contabilizacion', 'kilos', 'codigo_envio'];

/**
 * The start body of a complemento run of SGX for August 2026.
 *
 * @param  array<string, mixed>  $overrides
 * @return array<string, mixed>
 */
function complementoRun(array $overrides = []): array
{
    return array_merge([
        'conjunto' => 'VENTAS',
        'empresa' => 'SGX',
        'tipo' => 'complemento',
        'partes' => ['ventas' => 'todo'],
        'solicitudes' => [],
        'fecha_corte' => null,
        'ventana_desde' => '2026-08-01',
        'ventana_hasta' => '2026-08-31',
        'extraida_en' => '2026-10-16T09:58:00-05:00',
    ], $overrides);
}

/**
 * A VENTAS line already stored, without kilos nor codigo_envio.
 *
 * @return array<string, mixed>
 */
function complementoStoredLine(string $company, int $entry, string $postedOn, int $line = 0): array
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
 * One line of a complemento batch, by column name.
 *
 * @return array<string, mixed>
 */
function complementoLine(int $entry, string $postedOn, ?string $kilos, int $line = 0, ?string $code = 'CEDI-01'): array
{
    return [
        'tipo_objeto' => 13, 'doc_entry' => $entry, 'linea' => $line, 'fecha_contabilizacion' => $postedOn,
        'kilos' => $kilos, 'codigo_envio' => $code,
    ];
}

/**
 * A complemento batch body with the given header, by default the reduced one.
 *
 * @param  list<array<string, mixed>>  $lines
 * @param  list<string>  $columns
 * @return array<string, mixed>
 */
function complementoBatch(int $number, array $lines, array $columns = COMPLEMENTO_COLUMNS): array
{
    return [
        'batch' => $number,
        'parte' => 'ventas',
        'columns' => $columns,
        'rows' => array_map(fn (array $line): array => array_map(fn (string $column): mixed => $line[$column] ?? null, $columns), $lines),
    ];
}

/**
 * Opens a complemento run, sends the lines in one batch and returns the run id.
 *
 * @param  list<array<string, mixed>>  $lines
 * @param  array<string, mixed>  $overrides
 */
function sendComplemento(TestCase $test, array $lines, array $overrides = []): int
{
    $run = (int) RobotClient::post($test, '/api/robot/v1/corridas', complementoRun($overrides))->assertCreated()->json('run_id');
    RobotClient::post($test, "/api/robot/v1/corridas/{$run}/lotes", complementoBatch(1, $lines))->assertCreated();

    return $run;
}

function closeComplemento(TestCase $test, int $run, int $rows, ?int $sap = null): TestResponse
{
    return RobotClient::post($test, "/api/robot/v1/corridas/{$run}/cerrar", [
        'batches' => 1, 'filas' => ['ventas' => $rows], 'conteo_sap' => ['ventas' => $sap ?? $rows],
    ]);
}

/** @return list<array<string, mixed>> Every stored line with all its columns, sorted by company and key. */
function complementoSnapshot(): array
{
    return DB::connection('ventas')->table('ventas')->orderBy('empresa')->orderBy('doc_entry')->orderBy('linea')->get()
        ->map(fn (object $row): array => (array) $row)->all();
}

/** @return array<string, array{kilos: float|null, codigo_envio: string|null}> The kilos and codigo_envio of every stored line by "<empresa>/<doc_entry>/<linea>". */
function storedComplemento(): array
{
    return DB::connection('ventas')->table('ventas')->orderBy('empresa')->orderBy('doc_entry')->orderBy('linea')->get()
        ->mapWithKeys(fn (object $row): array => ["{$row->empresa}/{$row->doc_entry}/{$row->linea}" => [
            'kilos' => $row->kilos === null ? null : (float) $row->kilos,
            'codigo_envio' => $row->codigo_envio,
        ]])
        ->all();
}

/** @return list<array<string, mixed>> The month the tests load: SGX lines in and around August and an SDC line with a SGX key. */
function complementoMonth(): array
{
    return [
        complementoStoredLine('SGX', 1, '2026-08-01'),
        complementoStoredLine('SGX', 1, '2026-08-01', 1),
        complementoStoredLine('SGX', 2, '2026-08-31'),
        // Outside the range: neither filled nor missing.
        complementoStoredLine('SGX', 9, '2026-07-31'),
        complementoStoredLine('SGX', 10, '2026-09-24'),
        // Another company's line with the same key as an SGX one.
        complementoStoredLine('SDC', 1, '2026-08-01'),
    ];
}

it('fills only the kilos and codigo_envio of the company lines of the month and touches nothing else', function () {
    DB::connection('ventas')->table('ventas')->insert(complementoMonth());
    $before = complementoSnapshot();

    $run = sendComplemento($this, [
        complementoLine(1, '2026-08-01', '12.500000', code: '  CEDI-01 '),
        complementoLine(1, '2026-08-01', '-3.250000', 1, null),
        complementoLine(2, '2026-08-31', null, code: 'BOD-02'),
    ]);

    closeComplemento($this, $run, 3)
        ->assertOk()
        ->assertJsonPath('estado', 'cerrada')
        ->assertJsonPath('conteo.ventas', ['sap' => 3, 'recibidas' => 3, 'activas_recibidas' => 3, 'activas_mysql' => 3, 'cuadra' => true]);

    $untouched = fn (array $rows): array => array_map(fn (array $row): array => array_diff_key($row, ['kilos' => true, 'codigo_envio' => true]), $rows);
    $empty = ['kilos' => null, 'codigo_envio' => null];

    expect(storedComplemento())->toBe([
        'SDC/1/0' => $empty,
        'SGX/1/0' => ['kilos' => 12.5, 'codigo_envio' => 'CEDI-01'],
        'SGX/1/1' => ['kilos' => -3.25, 'codigo_envio' => null],
        'SGX/2/0' => ['kilos' => null, 'codigo_envio' => 'BOD-02'],
        'SGX/9/0' => $empty,
        'SGX/10/0' => $empty,
    ])
        // Every other column, sincronizado_en and corrida_id included, stays as it was.
        ->and($untouched(complementoSnapshot()))->toBe($untouched($before))
        ->and(Run::find($run)->tipo->value)->toBe('complemento')
        // A complemento load never stands for the nightly count of the day.
        ->and(DB::table('daily_counts')->count())->toBe(0);
});

it('writes a null over a value already filled', function () {
    DB::connection('ventas')->table('ventas')->insert([
        [...complementoStoredLine('SGX', 1, '2026-08-01'), 'kilos' => '7.000000', 'codigo_envio' => 'OLD'],
    ]);

    closeComplemento($this, sendComplemento($this, [complementoLine(1, '2026-08-01', null, code: null)]), 1)->assertOk();

    expect(storedComplemento())->toBe(['SGX/1/0' => ['kilos' => null, 'codigo_envio' => null]]);
});

it('rewrites the same kilos and codigo_envio when the month runs again, with no 409', function () {
    DB::connection('ventas')->table('ventas')->insert(complementoMonth());
    $lines = [
        complementoLine(1, '2026-08-01', '12.500000'),
        complementoLine(1, '2026-08-01', '-3.250000', 1, 'CEDI-02'),
        complementoLine(2, '2026-08-31', '4.000000', code: null),
    ];

    closeComplemento($this, sendComplemento($this, $lines), 3)->assertOk();
    $first = complementoSnapshot();

    closeComplemento($this, sendComplemento($this, $lines), 3)->assertOk();

    expect(complementoSnapshot())->toBe($first)
        ->and(storedComplemento()['SGX/1/1'])->toBe(['kilos' => -3.25, 'codigo_envio' => 'CEDI-02'])
        ->and(storedComplemento()['SGX/2/0'])->toBe(['kilos' => 4.0, 'codigo_envio' => null]);
});

it('fails the close and changes nothing when a line is not stored for the company in the range', function () {
    DB::connection('ventas')->table('ventas')->insert(complementoMonth());
    $before = complementoSnapshot();

    // Line 9 is stored but in July; line 3 is not stored at all.
    $run = sendComplemento($this, [
        complementoLine(1, '2026-08-01', '1.000000'), complementoLine(1, '2026-08-01', '1.000000', 1), complementoLine(2, '2026-08-31', '1.000000'),
        complementoLine(3, '2026-08-15', '1.000000'),
    ]);

    closeComplemento($this, $run, 4)
        ->assertUnprocessable()
        ->assertJsonPath('sobran', 1)
        ->assertJsonPath('faltan', 0)
        ->assertJsonValidationErrorFor('filas.ventas');

    expect(complementoSnapshot())->toBe($before)
        ->and(Run::find($run)->estado)->toBe(RunState::Failed);
});

it('does not take a line of another company as stored', function () {
    DB::connection('ventas')->table('ventas')->insert([complementoStoredLine('SDC', 1, '2026-08-01')]);

    $run = sendComplemento($this, [complementoLine(1, '2026-08-01', '1.000000')]);

    closeComplemento($this, $run, 1)->assertUnprocessable()->assertJsonPath('sobran', 1)->assertJsonPath('faltan', 0);

    expect(storedComplemento())->toBe(['SDC/1/0' => ['kilos' => null, 'codigo_envio' => null]]);
});

it('fails the close and changes nothing when a stored line of the range did not arrive', function () {
    DB::connection('ventas')->table('ventas')->insert(complementoMonth());
    $before = complementoSnapshot();

    $run = sendComplemento($this, [complementoLine(1, '2026-08-01', '1.000000'), complementoLine(2, '2026-08-31', '1.000000')]);

    closeComplemento($this, $run, 2)
        ->assertUnprocessable()
        ->assertJsonPath('sobran', 0)
        ->assertJsonPath('faltan', 1)
        ->assertJsonPath('message', 'Las líneas recibidas no cuadran con las de MySQL en el rango; la corrida complemento falló y no se cambió ninguna línea.')
        ->assertJsonValidationErrorFor('filas.ventas');

    expect(complementoSnapshot())->toBe($before)
        ->and(Run::find($run)->estado)->toBe(RunState::Failed)
        ->and(Run::find($run)->error)->toContain('sobran 0')->toContain('faltan 1');
});

it('fails the close and changes nothing when the SAP count differs from the lines received', function () {
    DB::connection('ventas')->table('ventas')->insert(complementoMonth());
    $before = complementoSnapshot();

    $run = sendComplemento($this, [complementoLine(1, '2026-08-01', '1.000000'), complementoLine(1, '2026-08-01', '1.000000', 1), complementoLine(2, '2026-08-31', '1.000000')]);

    closeComplemento($this, $run, 3, sap: 4)
        ->assertUnprocessable()
        ->assertJsonPath('message', 'El conteo de SAP no cuadra con las filas recibidas; la corrida complemento falló y no se cambió ninguna línea.')
        ->assertJsonValidationErrorFor('conteo_sap.ventas');

    expect(complementoSnapshot())->toBe($before)
        ->and(Run::find($run)->estado)->toBe(RunState::Failed);
});

it('requires the SAP count to close a complemento run', function () {
    DB::connection('ventas')->table('ventas')->insert(complementoMonth());
    $run = sendComplemento($this, [complementoLine(1, '2026-08-01', '1.000000')]);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['ventas' => 1]])
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('conteo_sap');
});

it('opens a complemento run on a range that already has lines', function () {
    DB::connection('ventas')->table('ventas')->insert(complementoMonth());

    RobotClient::post($this, '/api/robot/v1/corridas', complementoRun())->assertCreated();

    expect(Run::sole()->ventana_hasta?->toDateString())->toBe('2026-08-31');
});

it('refuses the old kilos run type', function () {
    RobotClient::post($this, '/api/robot/v1/corridas', complementoRun(['tipo' => 'kilos']))
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('tipo');
});

it('accepts January 2025 and the days of the month before the nightly window', function (array $range) {
    RobotClient::post($this, '/api/robot/v1/corridas', complementoRun($range))->assertCreated();
})->with([
    'January 2025' => [['ventana_desde' => '2025-01-01', 'ventana_hasta' => '2025-01-31']],
    'up to the day before the nightly window' => [['ventana_desde' => '2026-09-01', 'ventana_hasta' => '2026-09-23']],
]);

it('refuses a complemento range that is not within one month before the nightly window', function (array $range, string $field) {
    RobotClient::post($this, '/api/robot/v1/corridas', complementoRun($range))
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

it('refuses a complemento run of any other dataset', function (string $dataset) {
    RobotClient::post($this, '/api/robot/v1/corridas', complementoRun(['conjunto' => $dataset, 'partes' => ['pedidos' => 'todo']]))
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('tipo');
})->with(['MAESTROS', 'CARTERA', 'PEDIDOS', 'PRODUCCION']);

it('takes only the reduced header in a complemento batch', function (array $columns) {
    $run = (int) RobotClient::post($this, '/api/robot/v1/corridas', complementoRun())->assertCreated()->json('run_id');
    $line = RobotClient::row(Part::Sales, [
        'doc_entry' => 1, 'fecha_contabilizacion' => '2026-08-01', 'fecha_documento' => '2026-08-01', 'kilos' => '1.000000', 'codigo_envio' => 'CEDI-01',
    ]);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", complementoBatch(1, [$line], $columns))
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('columns');
})->with([
    'the full sales header' => [array_keys(Part::Sales->columns())],
    'without kilos' => [['tipo_objeto', 'doc_entry', 'linea', 'fecha_contabilizacion', 'codigo_envio']],
    'without codigo_envio' => [['tipo_objeto', 'doc_entry', 'linea', 'fecha_contabilizacion', 'kilos']],
    'with another sales column' => [[...COMPLEMENTO_COLUMNS, 'total']],
]);

it('takes the reduced header in any order, null values, and refuses a line outside the range', function () {
    $run = (int) RobotClient::post($this, '/api/robot/v1/corridas', complementoRun())->assertCreated()->json('run_id');
    $columns = ['codigo_envio', 'kilos', 'linea', 'fecha_contabilizacion', 'doc_entry', 'tipo_objeto'];

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", complementoBatch(1, [
        complementoLine(1, '2026-08-01', null, code: null), complementoLine(2, '2026-07-31', '1.000000'), complementoLine(3, '2026-08-15', '1.000000'),
    ], $columns))
        ->assertUnprocessable()
        ->assertJsonValidationErrors(['rows.1.fecha_contabilizacion'])
        ->assertJsonMissingValidationErrors(['rows.0.kilos', 'rows.0.codigo_envio', 'rows.0.fecha_contabilizacion', 'rows.2.fecha_contabilizacion']);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", complementoBatch(1, [
        complementoLine(2, '2026-07-31', '1.000000'), complementoLine(3, '2026-09-01', '1.000000'), complementoLine(4, '2026-08-15', '1.000000'),
    ], $columns))
        ->assertUnprocessable()
        ->assertJsonValidationErrors(['rows.0.fecha_contabilizacion', 'rows.1.fecha_contabilizacion'])
        ->assertJsonMissingValidationErrors(['rows.2.fecha_contabilizacion']);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", complementoBatch(1, [
        complementoLine(4, '2026-08-15', '1.000000'), complementoLine(5, '2026-08-16', null, code: null),
    ], $columns))
        ->assertCreated();
});

it('cuts a codigo_envio longer than 50 characters, as in a full run', function () {
    DB::connection('ventas')->table('ventas')->insert([complementoStoredLine('SGX', 1, '2026-08-01')]);

    closeComplemento($this, sendComplemento($this, [complementoLine(1, '2026-08-01', '1.000000', code: str_repeat('X', 55))]), 1)->assertOk();

    expect(storedComplemento()['SGX/1/0']['codigo_envio'])->toBe(str_repeat('X', 50));
});

it('refuses a key repeated across the batches of a complemento run', function () {
    $run = (int) RobotClient::post($this, '/api/robot/v1/corridas', complementoRun())->assertCreated()->json('run_id');

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", complementoBatch(1, [complementoLine(1, '2026-08-01', '1.000000')]))->assertCreated();
    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", complementoBatch(2, [complementoLine(1, '2026-08-01', '2.000000')]))
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('rows.0.tipo_objeto');
});
