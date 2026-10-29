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
    return Run::create(array_merge([
        'conjunto' => $dataset, 'empresa' => $company, 'tipo' => 'solicitud', 'partes' => ['clientes' => 'cambios'],
        'solicitudes' => [], 'extraida_en' => '2026-10-27 02:00:00', 'estado' => 'cerrada',
        'abierta_hasta' => '2026-10-27 02:30:00', 'robot_key' => 'r2026a',
    ], $attributes));
}

it('lists every company and dataset in enum order', function () {
    $statuses = app(DatasetStatuses::class)->all();

    expect(array_map(fn (DatasetStatusData $status): string => $status->company->value.' '.$status->dataset->value, $statuses))
        ->toBe(['SGX MAESTROS', 'SGX CARTERA', 'SDC MAESTROS', 'SDC CARTERA'])
        ->and($statuses[0]->lastAppliedAt)->toBeNull()
        ->and($statuses[0]->lastRun)->toBeNull()
        ->and($statuses[0]->rows)->toHaveCount(count(Part::forDataset(Dataset::Maestros)))
        ->and($statuses[1]->rows)->toBe(['cartera' => 0]);
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

it('counts the active master rows and every receivable line of each company', function () {
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

    $statuses = app(DatasetStatuses::class)->all();

    expect($statuses[0]->rows['clientes'])->toBe(2)
        ->and($statuses[0]->rows['articulos'])->toBe(0)
        ->and($statuses[1]->rows)->toBe(['cartera' => 3])
        ->and($statuses[2]->rows['clientes'])->toBe(1)
        ->and($statuses[3]->rows)->toBe(['cartera' => 0]);
});
