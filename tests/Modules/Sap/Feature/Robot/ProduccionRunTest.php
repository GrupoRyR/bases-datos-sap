<?php

use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Domain\Runs\RunState;
use App\Modules\Sap\Models\Run;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Tests\Modules\Sap\Support\RobotClient;
use Tests\TestCase;

/*
| A PRODUCCION run (docs/contrato-robot.md, sections 4 and 12): six parts of
| SGX only, all in mode todo. The three movement parts bring the rows dated
| from the window on and their close replaces only that window; the three
| master parts are replaced whole. An empty part fails the run.
*/

beforeEach(function () {
    RobotClient::configure();
    // On 18/11 the query's window starts on 25/10.
    Carbon::setTestNow(Carbon::parse('2026-11-18 10:00:00', 'America/Bogota'));
});

/** @return array<string, string> Every PRODUCCION part in mode todo. */
function produccionParts(): array
{
    return array_fill_keys(array_map(fn (Part $part): string => $part->value, Part::forDataset(Dataset::Produccion)), 'todo');
}

/**
 * The start body of a PRODUCCION run of SGX with its window.
 *
 * @param  array<string, mixed>  $overrides
 * @return array<string, mixed>
 */
function produccionRun(array $overrides = []): array
{
    return array_merge([
        'conjunto' => 'PRODUCCION',
        'empresa' => 'SGX',
        'tipo' => 'solicitud',
        'partes' => produccionParts(),
        'solicitudes' => [],
        'fecha_corte' => null,
        'ventana_desde' => '2026-10-25',
        'extraida_en' => '2026-11-18T09:58:00-05:00',
    ], $overrides);
}

/**
 * A row of the part as the robot sends it, dated inside the window when the
 * part has one.
 *
 * @param  array<string, mixed>  $overrides
 * @return array<string, mixed>
 */
function productionRow(Part $part, array $overrides = []): array
{
    $dated = $part->windowColumn() === null ? [] : [$part->windowColumn() => '2026-11-02'];

    return RobotClient::row($part, [...$dated, ...$overrides]);
}

/**
 * A row already in ventas_sap.
 *
 * @param  array<string, mixed>  $overrides
 * @return array<string, mixed>
 */
function storedProduction(Part $part, array $overrides = []): array
{
    return [...productionRow($part, $overrides), 'empresa' => 'SGX', 'sincronizado_en' => '2026-11-17 02:30:00'];
}

/**
 * Opens a PRODUCCION run, sends each part's rows in its own batch and
 * returns the run id and the rows sent per part.
 *
 * @param  array<string, list<array<string, mixed>>>  $rows  Rows by part name.
 * @param  array<string, mixed>  $overrides
 * @return array{0: int, 1: int, 2: array<string, int>}
 */
function sendProduccion(TestCase $test, array $rows, array $overrides = []): array
{
    $run = (int) RobotClient::post($test, '/api/robot/v1/corridas', produccionRun($overrides))->assertCreated()->json('run_id');
    $batch = 0;
    $sent = array_map(fn (): int => 0, produccionParts());

    foreach ($rows as $name => $partRows) {
        RobotClient::post($test, "/api/robot/v1/corridas/{$run}/lotes", RobotClient::batch(++$batch, Part::from($name), $partRows))->assertCreated();
        $sent[$name] = count($partRows);
    }

    return [$run, $batch, $sent];
}

/**
 * One valid row of every part, with the overrides given by part name.
 *
 * @param  array<string, list<array<string, mixed>>>  $overrides
 * @return array<string, list<array<string, mixed>>>
 */
function produccionRows(array $overrides = []): array
{
    $rows = [];

    foreach (Part::forDataset(Dataset::Produccion) as $part) {
        $rows[$part->value] = $overrides[$part->value] ?? [productionRow($part)];
    }

    return $rows;
}

/** @return list<string> "<fecha>/<codigo_articulo>" of the part's stored rows, sorted. */
function storedProductionRows(Part $part, string $label = 'codigo_articulo'): array
{
    $date = $part->windowColumn();

    return DB::connection('ventas')->table($part->table())->get()
        ->map(fn (object $row): string => ($date === null ? '' : "{$row->{$date}}/").$row->{$label})
        ->sort()->values()->all();
}

it('opens a PRODUCCION run with its window and the six parts in mode todo', function () {
    RobotClient::post($this, '/api/robot/v1/corridas', produccionRun())->assertCreated();

    $run = Run::sole();

    expect($run->ventana_desde?->toDateString())->toBe('2026-10-25')
        ->and($run->fecha_corte)->toBeNull()
        // MySQL reorders the keys of a JSON object, so compare parts and modes, not their order.
        ->and($run->partes)->toEqual(produccionParts());
});

it('accepts a window from 2026-01-01 to tomorrow, so the initial load can reach back months', function (string $from) {
    RobotClient::post($this, '/api/robot/v1/corridas', produccionRun(['ventana_desde' => $from]))->assertCreated();
})->with(['2026-01-01', '2026-08-01', '2026-11-19']);

it('refuses a PRODUCCION run without a valid window, with a cut-off date, in changes or missing parts', function (array $overrides, string $field) {
    RobotClient::post($this, '/api/robot/v1/corridas', produccionRun($overrides))
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor($field);

    expect(Run::count())->toBe(0);
})->with([
    'without window' => [['ventana_desde' => null], 'ventana_desde'],
    'window not a date' => [['ventana_desde' => '2026-8-01'], 'ventana_desde'],
    'impossible window' => [['ventana_desde' => '2026-02-30'], 'ventana_desde'],
    'window after tomorrow' => [['ventana_desde' => '2026-11-20'], 'ventana_desde'],
    'window before 2026' => [['ventana_desde' => '2025-12-31'], 'ventana_desde'],
    'cut-off date' => [['fecha_corte' => '2026-11-17'], 'fecha_corte'],
    'in changes' => [['partes' => [...produccionParts(), 'produccion_rutas' => 'cambios']], 'partes.produccion_rutas'],
    'part of another dataset' => [['partes' => ['ventas' => 'todo']], 'partes.ventas'],
    'full run without every part' => [['tipo' => 'completa', 'partes' => ['produccion_costos' => 'todo']], 'partes'],
]);

it('refuses a PRODUCCION run of SDC, since the BEAS tables are Segurex only', function () {
    RobotClient::post($this, '/api/robot/v1/corridas', produccionRun(['empresa' => 'SDC']))
        ->assertUnprocessable()
        ->assertJsonPath('errors.empresa.0', 'PRODUCCION es solo de SGX.');

    expect(Run::count())->toBe(0);
});

it('refuses a movement row dated before the window', function (Part $part) {
    [$run] = sendProduccion($this, []);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", RobotClient::batch(1, $part, [
        productionRow($part, ['fecha' => '2026-10-25']),
        productionRow($part, ['fecha' => '2026-10-24', 'doc_entry' => 2]),
    ]))->assertUnprocessable()
        ->assertJsonValidationErrors(['rows.1.fecha' => 'Es anterior a ventana_desde (2026-10-25).'])
        ->assertJsonMissingValidationErrors(['rows.0.fecha']);

    expect(Run::find($run)->lotes_rechazados)->toBe(1)
        ->and(DB::table('robot_batches')->count())->toBe(0);
})->with([Part::ProductionFinished, Part::PlantLoad, Part::ProductionCosts]);

it('refuses a key repeated in the keyed parts and keeps repeated rows in the others', function () {
    [$run] = sendProduccion($this, [
        'produccion_terminado' => [productionRow(Part::ProductionFinished, ['doc_entry' => 81, 'linea' => 0])],
        'produccion_costeo_teorico' => [productionRow(Part::StandardCosts, ['codigo_articulo' => 'PT-100'])],
        // Two equal plant reports of the same day are legitimate.
        'produccion_carga_planta' => [productionRow(Part::PlantLoad), productionRow(Part::PlantLoad)],
    ]);
    $path = "/api/robot/v1/corridas/{$run}/lotes";

    RobotClient::post($this, $path, RobotClient::batch(4, Part::ProductionFinished, [productionRow(Part::ProductionFinished, ['doc_entry' => 81, 'linea' => 0])]))
        ->assertUnprocessable()
        ->assertJsonValidationErrors(['rows.0.doc_entry']);
    RobotClient::post($this, $path, RobotClient::batch(4, Part::StandardCosts, [productionRow(Part::StandardCosts, ['codigo_articulo' => 'PT-100'])]))
        ->assertUnprocessable()
        ->assertJsonValidationErrors(['rows.0.codigo_articulo']);
    RobotClient::post($this, $path, RobotClient::batch(4, Part::PlantLoad, [productionRow(Part::PlantLoad)]))->assertCreated();
});

it('accepts each of the five cost concepts and refuses any other text', function () {
    [$run] = sendProduccion($this, []);
    $concepts = ['Mano de obra directa', 'Costo variable', 'Costo fijo', 'Material comprado', 'Material intermedio'];
    $path = "/api/robot/v1/corridas/{$run}/lotes";

    RobotClient::post($this, $path, RobotClient::batch(1, Part::ProductionCosts, array_map(
        fn (string $concept): array => productionRow(Part::ProductionCosts, ['concepto' => $concept]),
        $concepts,
    )))->assertCreated();

    RobotClient::post($this, $path, RobotClient::batch(2, Part::ProductionCosts, [
        productionRow(Part::ProductionCosts, ['concepto' => 'Material Intermedio']),
        productionRow(Part::ProductionCosts, ['concepto' => 'Mano de obra']),
    ]))->assertUnprocessable()
        ->assertJsonValidationErrors(['rows.0.concepto', 'rows.1.concepto']);
});

it('replaces only the window of the movement parts and every row of the masters', function () {
    DB::connection('ventas')->table('produccion_costos')->insert([
        // Before the window: kept as it was.
        storedProduction(Part::ProductionCosts, ['fecha' => '2026-10-24', 'codigo_articulo' => 'OLD-1']),
        // Inside the window: replaced by what the run brings.
        storedProduction(Part::ProductionCosts, ['fecha' => '2026-10-25', 'codigo_articulo' => 'OLD-2']),
    ]);
    DB::connection('ventas')->table('produccion_rutas')->insert(storedProduction(Part::Routings, ['codigo_articulo' => 'OLD-R']));
    DB::connection('ventas')->table('pedidos')->insert([...RobotClient::row(Part::Orders), 'empresa' => 'SGX', 'sincronizado_en' => '2026-11-17 02:30:00']);

    [$run, $batches, $sent] = sendProduccion($this, produccionRows([
        'produccion_costos' => [
            productionRow(Part::ProductionCosts, ['fecha' => '2026-10-25', 'codigo_articulo' => 'NEW-1']),
            productionRow(Part::ProductionCosts, ['fecha' => '2026-11-17', 'codigo_articulo' => 'NEW-2']),
        ],
        'produccion_rutas' => [productionRow(Part::Routings, ['codigo_articulo' => 'NEW-R'])],
    ]));

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => $batches, 'filas' => $sent])
        ->assertOk()
        ->assertJsonPath('estado', 'cerrada');

    $synced = DB::connection('ventas')->table('produccion_costos')->where('codigo_articulo', 'NEW-1')->value('sincronizado_en');

    expect(storedProductionRows(Part::ProductionCosts))->toBe(['2026-10-24/OLD-1', '2026-10-25/NEW-1', '2026-11-17/NEW-2'])
        ->and(storedProductionRows(Part::Routings))->toBe(['NEW-R'])
        ->and(DB::connection('ventas')->table('produccion_terminado')->count())->toBe(1)
        ->and(DB::connection('ventas')->table('produccion_costos')->where('codigo_articulo', 'NEW-1')->value('corrida_id'))->toBe($run)
        ->and($synced)->not->toBeNull()
        // Other datasets on the same connection stay as they were.
        ->and(DB::connection('ventas')->table('pedidos')->count())->toBe(1);
});

it('never touches the rows of another company', function () {
    // PRODUCCION is SGX only, but the close still filters by company.
    $other = fn (Part $part, string $item): array => [...storedProduction($part, ['codigo_articulo' => $item]), 'empresa' => 'SDC'];
    DB::connection('ventas')->table('produccion_costos')->insert($other(Part::ProductionCosts, 'SDC-1'));
    DB::connection('ventas')->table('produccion_rutas')->insert($other(Part::Routings, 'SDC-R'));

    [$run, $batches, $sent] = sendProduccion($this, produccionRows());

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => $batches, 'filas' => $sent])->assertOk();

    expect(DB::connection('ventas')->table('produccion_costos')->where('empresa', 'SDC')->pluck('codigo_articulo')->all())->toBe(['SDC-1'])
        ->and(DB::connection('ventas')->table('produccion_rutas')->where('empresa', 'SDC')->pluck('codigo_articulo')->all())->toBe(['SDC-R'])
        ->and(DB::connection('ventas')->table('produccion_rutas')->where('empresa', 'SGX')->count())->toBe(1);
});

it('fails a close with an empty part and changes nothing', function () {
    DB::connection('ventas')->table('produccion_rutas')->insert(storedProduction(Part::Routings, ['codigo_articulo' => 'OLD-R']));
    $rows = produccionRows();
    unset($rows['produccion_rutas']);
    [$run, $batches, $sent] = sendProduccion($this, $rows);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => $batches, 'filas' => $sent])
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('filas.produccion_rutas');

    expect(Run::find($run)->estado)->toBe(RunState::Failed)
        ->and(storedProductionRows(Part::Routings))->toBe(['OLD-R'])
        ->and(DB::connection('ventas')->table('produccion_costos')->count())->toBe(0);
});

it('counts the window rows of the movement parts and every row of the masters in the nightly run', function () {
    DB::connection('ventas')->table('produccion_costos')->insert(storedProduction(Part::ProductionCosts, ['fecha' => '2026-10-01']));
    [$run, $batches, $sent] = sendProduccion($this, produccionRows([
        'produccion_costos' => [productionRow(Part::ProductionCosts), productionRow(Part::ProductionCosts)],
        'produccion_despiece' => [productionRow(Part::BillOfMaterials), productionRow(Part::BillOfMaterials), productionRow(Part::BillOfMaterials)],
    ]), ['tipo' => 'completa']);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => $batches, 'filas' => $sent, 'conteo_sap' => [...$sent, 'produccion_rutas' => 2]])
        ->assertOk()
        ->assertJsonPath('conteo.produccion_costos', ['sap' => 2, 'recibidas' => 2, 'activas_recibidas' => 2, 'activas_mysql' => 2, 'cuadra' => true])
        ->assertJsonPath('conteo.produccion_despiece', ['sap' => 3, 'recibidas' => 3, 'activas_recibidas' => 3, 'activas_mysql' => 3, 'cuadra' => true])
        // A count that does not match SAP is recorded without failing the run.
        ->assertJsonPath('conteo.produccion_rutas.cuadra', false)
        ->assertJsonPath('estado', 'cerrada');

    expect(DB::table('daily_counts')->where('conjunto', 'PRODUCCION')->count())->toBe(6)
        ->and(DB::table('daily_counts')->where('parte', 'produccion_costos')->value('fecha'))->toStartWith('2026-11-18');
});
