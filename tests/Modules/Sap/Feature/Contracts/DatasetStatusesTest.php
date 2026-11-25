<?php

use App\Modules\Sap\Contracts\Data\DatasetStatusData;
use App\Modules\Sap\Contracts\DatasetStatuses;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Models\Run;
use Illuminate\Support\Facades\DB;

/*
| The status of each dataset of each company, read by the panel through
| Contracts\DatasetStatuses: last applied, rows in MySQL and latest run.
*/

beforeEach(function () {
    $this->travelTo(now()->setDate(2026, 10, 27)->setTime(10, 0));
});

/** @param  array<string, mixed>  $attributes */
function statusRun(Company $company, Dataset $dataset, array $attributes): Run
{
    return Run::forceCreate(array_merge([
        'conjunto' => $dataset, 'empresa' => $company, 'tipo' => 'solicitud', 'partes' => ['clientes' => 'cambios'],
        'solicitudes' => [], 'extraida_en' => '2026-10-27 02:00:00', 'estado' => 'cerrada',
        'abierta_hasta' => '2026-10-27 02:30:00', 'robot_key' => 'r2026a',
    ], $attributes));
}

it('lists every company and dataset in enum order, PRODUCCION only for SGX', function () {
    $statuses = app(DatasetStatuses::class)->all();

    expect(array_map(fn (DatasetStatusData $status): string => $status->company->value.' '.$status->dataset->value, $statuses))
        ->toBe(['SGX MAESTROS', 'SGX CARTERA', 'SGX VENTAS', 'SGX PEDIDOS', 'SGX PRODUCCION', 'SDC MAESTROS', 'SDC CARTERA', 'SDC VENTAS', 'SDC PEDIDOS'])
        ->and($statuses[0]->lastAppliedAt)->toBeNull()
        ->and($statuses[0]->lastRun)->toBeNull()
        ->and($statuses[0]->rows)->toHaveCount(count(Part::forDataset(Dataset::Maestros)))
        ->and($statuses[1]->rows)->toBe(['cartera' => 0])
        ->and($statuses[2]->rows)->toBe(['ventas' => 0])
        ->and($statuses[3]->rows)->toBe(['pedidos' => 0])
        ->and(array_keys($statuses[4]->rows))->toBe(array_map(fn (Part $part): string => $part->value, Part::forDataset(Dataset::Produccion)));
});

it('tells the last applied time and the latest run in any state', function () {
    statusRun(Company::Sgx, Dataset::Maestros, ['tipo' => 'completa', 'aplicada_en' => '2026-10-27 02:30:00', 'terminada_en' => '2026-10-27 02:30:00']);
    statusRun(Company::Sgx, Dataset::Maestros, ['aplicada_en' => '2026-10-27 09:00:00', 'terminada_en' => '2026-10-27 09:00:00']);
    $failed = statusRun(Company::Sgx, Dataset::Maestros, [
        'estado' => 'fallida', 'error' => 'VPN no conectó', 'terminada_en' => '2026-10-27 09:40:00',
    ]);
    // Another company does not leak into SGX.
    statusRun(Company::Sdc, Dataset::Maestros, ['aplicada_en' => '2026-10-27 09:50:00']);

    $sgx = app(DatasetStatuses::class)->all()[0];

    expect($sgx->lastAppliedAt?->format('Y-m-d H:i'))->toBe('2026-10-27 09:00')
        ->and($sgx->lastAppliedAt?->getTimezone()->getName())->toBe('America/Bogota')
        ->and($sgx->lastRun?->id)->toBe($failed->id)
        ->and($sgx->lastRun?->type)->toBe('solicitud')
        ->and($sgx->lastRun?->state)->toBe('fallida')
        ->and($sgx->lastRun?->error)->toBe('VPN no conectó')
        ->and($sgx->lastRun?->startedAt->format('Y-m-d H:i'))->toBe('2026-10-27 10:00')
        ->and($sgx->lastRun?->finishedAt?->format('H:i'))->toBe('09:40');
});

it('never shows a historical or kilos load as the last update or the latest run of VENTAS', function (string $type) {
    statusRun(Company::Sgx, Dataset::Ventas, ['tipo' => 'completa', 'partes' => ['ventas' => 'todo'], 'aplicada_en' => '2026-10-26 02:30:00']);
    $nightly = statusRun(Company::Sgx, Dataset::Ventas, [
        'tipo' => 'completa', 'partes' => ['ventas' => 'todo'], 'estado' => 'fallida',
        'error' => 'VPN no conectó', 'terminada_en' => '2026-10-27 02:10:00',
    ]);
    // A later load of a past month, applied after the failed nightly run.
    statusRun(Company::Sgx, Dataset::Ventas, [
        'tipo' => $type, 'partes' => ['ventas' => 'todo'], 'ventana_desde' => '2026-08-01', 'ventana_hasta' => '2026-08-31',
        'aplicada_en' => '2026-10-27 09:00:00', 'terminada_en' => '2026-10-27 09:00:00',
    ]);

    $ventas = app(DatasetStatuses::class)->all()[2];

    expect($ventas->dataset)->toBe(Dataset::Ventas)
        ->and($ventas->lastAppliedAt?->format('Y-m-d H:i'))->toBe('2026-10-26 02:30')
        ->and($ventas->lastRun?->id)->toBe($nightly->id)
        ->and($ventas->lastRun?->state)->toBe('fallida');
})->with(['historico', 'kilos']);

it('counts the active master rows and every receivable, sales and order line of each company', function () {
    $synced = '2026-10-27 02:30:00';
    DB::connection('maestros')->table('clientes')->insert([
        ['empresa' => 'SGX', 'codigo' => 'C1', 'nombre' => 'Uno', 'activo' => true, 'sincronizado_en' => $synced],
        ['empresa' => 'SGX', 'codigo' => 'C2', 'nombre' => 'Dos', 'activo' => true, 'sincronizado_en' => $synced],
        ['empresa' => 'SGX', 'codigo' => 'C3', 'nombre' => 'Tres', 'activo' => false, 'sincronizado_en' => $synced],
        ['empresa' => 'SDC', 'codigo' => 'C1', 'nombre' => 'Uno', 'activo' => true, 'sincronizado_en' => $synced],
    ]);
    DB::connection('cartera')->table('cartera')->insert(array_map(fn (string $document): array => [
        'empresa' => 'SGX', 'codigo_sn' => 'C1', 'documento' => $document, 'fecha_vencimiento' => '2026-10-01',
        'dias' => 26, 'saldo' => '1000.00', 'sincronizado_en' => $synced,
    ], ['F1', 'F2', 'F3']));
    // Sales lines have no flag: every line counts, inside the window or not.
    DB::connection('ventas')->table('ventas')->insert(array_map(fn (array $line): array => [
        'empresa' => 'SDC', 'tipo_objeto' => 13, 'doc_entry' => 500, 'linea' => $line[0], 'numero_documento' => 9001,
        'clase_documento' => 'factura', 'estado_documento' => 'abierto', 'fecha_documento' => $line[1],
        'fecha_contabilizacion' => $line[1], 'slp_code' => 1, 'codigo_cliente' => 'C1', 'cantidad' => '1.000000',
        'total' => '100.00', 'sincronizado_en' => $synced,
    ], [[0, '2026-08-14'], [1, '2026-10-20']]));
    // Order lines have no flag either: every open line of the company counts.
    DB::connection('ventas')->table('pedidos')->insert(array_map(fn (int $line): array => [
        'empresa' => 'SGX', 'doc_entry' => 3859, 'numero_pedido' => 3859, 'linea' => $line, 'fecha_pedido' => '2026-10-20',
        'fecha_compromiso' => '2026-10-30', 'dias' => 7, 'rango' => 'Hasta 30 dias', 'dias_atraso' => -3, 'slp_code' => 1,
        'codigo_cliente' => 'C1', 'codigo_articulo' => 'A1', 'cantidad_pedida' => '400.000000',
        'cantidad_pendiente' => '400.000000', 'total_pendiente' => '100.00', 'sincronizado_en' => $synced,
    ], [0, 1, 2]));

    $statuses = app(DatasetStatuses::class)->all();

    expect($statuses[0]->rows['clientes'])->toBe(2)
        ->and($statuses[0]->rows['articulos'])->toBe(0)
        ->and($statuses[1]->rows)->toBe(['cartera' => 3])
        ->and($statuses[2]->rows)->toBe(['ventas' => 0])
        ->and($statuses[3]->rows)->toBe(['pedidos' => 3])
        ->and($statuses[4]->rows['produccion_despiece'])->toBe(0)
        ->and($statuses[5]->rows['clientes'])->toBe(1)
        ->and($statuses[6]->rows)->toBe(['cartera' => 0])
        ->and($statuses[7]->rows)->toBe(['ventas' => 2])
        ->and($statuses[8]->rows)->toBe(['pedidos' => 0]);
});
