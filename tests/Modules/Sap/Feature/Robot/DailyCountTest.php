<?php

use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Models\Run;
use Illuminate\Support\Facades\DB;
use Tests\Modules\Sap\Support\RobotClient;
use Tests\TestCase;

/*
| The nightly count (docs/plan-bases-sap.md, section 6, and
| docs/contrato-robot.md, section 4.3): on closing a full run the API
| compares the SAP count the robot sends with the rows received and the
| active rows in MySQL after applying, and keeps the result of the day.
*/

beforeEach(function () {
    RobotClient::configure();
    $this->travelTo(now()->setDate(2026, 10, 27)->setTime(2, 20));
});

/**
 * Sends and closes a full MAESTROS run of SGX with one row per part (two
 * customers), with the given SAP counts. Returns the close response JSON.
 *
 * @param  array<string, int>  $sap
 * @return array<string, mixed>
 */
function closeFullMaestros(TestCase $test, array $sap = []): array
{
    $parts = array_map(fn (Part $part): string => $part->value, Part::forDataset(Dataset::Maestros));
    $run = RobotClient::openRun($test, ['tipo' => 'completa', 'partes' => array_fill_keys($parts, 'todo')]);
    $filas = [];

    foreach (Part::forDataset(Dataset::Maestros) as $number => $part) {
        $rows = $part === Part::Customers
            ? [RobotClient::row($part, ['codigo' => 'C1']), RobotClient::row($part, ['codigo' => 'C2'])]
            : [RobotClient::row($part)];
        RobotClient::post($test, "/api/robot/v1/corridas/{$run}/lotes", RobotClient::batch($number + 1, $part, $rows))->assertCreated();
        $filas[$part->value] = count($rows);
    }

    return RobotClient::post($test, "/api/robot/v1/corridas/{$run}/cerrar", [
        'batches' => count($filas), 'filas' => $filas, 'conteo_sap' => array_merge($filas, $sap),
    ])->assertOk()->json();
}

it('compares SAP, received and active MySQL rows per part and answers it', function () {
    $response = closeFullMaestros($this);

    expect($response['conteo']['clientes'])->toBe(['sap' => 2, 'recibidas' => 2, 'activas_mysql' => 2, 'cuadra' => true])
        ->and($response['conteo'])->toHaveCount(12)
        ->and(collect($response['conteo'])->every(fn (array $count): bool => $count['cuadra']))->toBeTrue();
});

it('records a mismatch without failing the run', function () {
    // SAP says 3 customers, but only 2 arrived.
    $response = closeFullMaestros($this, ['clientes' => 3]);

    expect($response['estado'])->toBe('cerrada')
        ->and($response['conteo']['clientes'])->toBe(['sap' => 3, 'recibidas' => 2, 'activas_mysql' => 2, 'cuadra' => false]);
});

it('counts the active rows in MySQL, so a stale active row breaks the match', function () {
    // An active customer of SDC does not count for SGX; an inactive one of SGX neither.
    DB::connection('maestros')->table('clientes')->insert([
        ['empresa' => 'SDC', 'codigo' => 'C9', 'nombre' => 'Otra empresa', 'activo' => true, 'sincronizado_en' => '2026-10-01 02:30:00'],
    ]);

    expect(closeFullMaestros($this)['conteo']['clientes']['activas_mysql'])->toBe(2);
});

it('keeps the result of the day for the panel, one row per company and part', function () {
    closeFullMaestros($this, ['marcas' => 5]);

    $brands = DB::table('daily_counts')->where('parte', 'marcas')->sole();

    expect(DB::table('daily_counts')->count())->toBe(12)
        ->and($brands->fecha)->toStartWith('2026-10-27')
        ->and($brands->empresa)->toBe('SGX')
        ->and($brands->conjunto)->toBe('MAESTROS')
        ->and([(int) $brands->sap, (int) $brands->recibidas, (int) $brands->activas_mysql, (bool) $brands->cuadra])->toBe([5, 1, 1, false])
        ->and((int) $brands->run_id)->toBe(Run::sole()->id);
});

it('replaces the result of the day when the full run runs again', function () {
    closeFullMaestros($this, ['marcas' => 5]);
    $this->travel(1)->hours();
    closeFullMaestros($this);

    expect(DB::table('daily_counts')->count())->toBe(12)
        ->and((bool) DB::table('daily_counts')->where('parte', 'marcas')->value('cuadra'))->toBeTrue();
});

it('counts CARTERA lines of the company after replacing them', function () {
    $run = RobotClient::openRun($this, ['conjunto' => 'CARTERA', 'empresa' => 'SDC', 'tipo' => 'completa', 'partes' => ['cartera' => 'todo'], 'fecha_corte' => '2026-10-26']);
    $lines = [RobotClient::row(Part::Receivables, ['documento' => 'FV-1']), RobotClient::row(Part::Receivables, ['documento' => 'FV-2'])];
    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", RobotClient::batch(1, Part::Receivables, $lines));

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['cartera' => 2], 'conteo_sap' => ['cartera' => 2]])
        ->assertOk()
        ->assertJsonPath('conteo.cartera', ['sap' => 2, 'recibidas' => 2, 'activas_mysql' => 2, 'cuadra' => true]);
});

it('neither answers nor records a count for a request run', function () {
    $run = RobotClient::openRun($this, ['partes' => ['clientes' => 'cambios']]);
    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", RobotClient::batch(1, Part::Customers, [RobotClient::row(Part::Customers)]));

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['clientes' => 1]])
        ->assertOk()
        ->assertJsonMissingPath('conteo');

    expect(DB::table('daily_counts')->count())->toBe(0);
});
