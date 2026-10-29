<?php

use App\Modules\Sap\Contracts\Data\StabilityDayData;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Contracts\Stability;
use App\Modules\Sap\Models\Run;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;

/*
| The stability counter of docs/plan-bases-sap.md, section 6, read by the
| panel through Contracts\Stability. Today is 2026-10-27 in Bogota.
*/

beforeEach(function () {
    $this->travelTo(now()->setDate(2026, 10, 27)->setTime(10, 0));
});

function stabilityRun(string $day, Company $company, Dataset $dataset, string $state = 'cerrada'): Run
{
    return Run::create([
        'conjunto' => $dataset, 'empresa' => $company, 'tipo' => 'completa', 'partes' => [], 'solicitudes' => [],
        'extraida_en' => "{$day} 02:10:00", 'estado' => $state, 'abierta_hasta' => "{$day} 02:40:00",
        'robot_key' => 'r2026a', 'terminada_en' => "{$day} 02:20:00",
    ]);
}

/** A day where every nightly run of every company and dataset closed and its count matched. */
function stabilityStableDay(string $day): void
{
    foreach (Company::cases() as $company) {
        foreach (Dataset::cases() as $dataset) {
            $run = stabilityRun($day, $company, $dataset);
            DB::table('daily_counts')->insert([
                'fecha' => $day, 'empresa' => $company->value, 'conjunto' => $dataset->value,
                'parte' => Part::forDataset($dataset)[0]->value, 'sap' => 5, 'recibidas' => 5, 'activas_mysql' => 5,
                'cuadra' => true, 'run_id' => $run->id, 'created_at' => now(), 'updated_at' => now(),
            ]);
        }
    }
}

/** Stable days from $from back, $days of them. */
function stabilityStableDays(string $from, int $days): void
{
    for ($i = 0; $i < $days; $i++) {
        stabilityStableDay(CarbonImmutable::parse($from)->subDays($i)->toDateString());
    }
}

function stabilityRequest(string $state, string $runFrom, ?string $finishedAt = null): int
{
    return DB::table('update_requests')->insertGetId([
        'empresa' => 'SGX', 'conjunto' => 'MAESTROS', 'estado' => $state, 'correr_desde' => $runFrom,
        'terminada_en' => $finishedAt, 'created_at' => $runFrom, 'updated_at' => $runFrom,
    ]);
}

/** @return array<string, StabilityDayData> */
function stabilityDays(): array
{
    return collect(app(Stability::class)->current()->days)
        ->keyBy(fn (StabilityDayData $day): string => $day->date->toDateString())
        ->all();
}

it('skips today while it is in progress and counts back from yesterday', function () {
    stabilityStableDays('2026-10-26', 7);

    $stability = app(Stability::class)->current();
    $today = $stability->days[0];

    expect($stability->stableDays)->toBe(7)
        ->and($stability->targetDays)->toBe(14)
        ->and($stability->days)->toHaveCount(14)
        ->and($today->date->format('Y-m-d H:i'))->toBe('2026-10-27 00:00')
        ->and($today->stable)->toBeFalse()
        ->and($today->problems)->toContain('No hubo corrida nocturna cerrada de SGX MAESTROS.', 'Falta el conteo de SDC CARTERA.')
        ->and($stability->days[13]->date->toDateString())->toBe('2026-10-14');
});

it('ends the streak today when something today already went wrong for good', function (string $failure) {
    stabilityStableDays('2026-10-26', 7);

    match ($failure) {
        'failed run' => stabilityRun('2026-10-27', Company::Sgx, Dataset::Cartera, 'fallida'),
        'count mismatch' => DB::table('daily_counts')->insert([
            'fecha' => '2026-10-27', 'empresa' => 'SGX', 'conjunto' => 'MAESTROS', 'parte' => 'clientes', 'sap' => 6,
            'recibidas' => 5, 'activas_mysql' => 5, 'cuadra' => false,
            'run_id' => stabilityRun('2026-10-27', Company::Sgx, Dataset::Maestros)->id, 'created_at' => now(), 'updated_at' => now(),
        ]),
        'late request' => stabilityRequest('terminada', '2026-10-27 08:00:00', '2026-10-27 08:20:00'),
    };

    expect(app(Stability::class)->current()->stableDays)->toBe(0);
})->with(['failed run', 'count mismatch', 'late request']);

it('counts today once it is stable', function () {
    stabilityStableDays('2026-10-27', 4);

    $stability = app(Stability::class)->current();

    expect($stability->stableDays)->toBe(4)
        ->and($stability->days[0]->stable)->toBeTrue()
        ->and($stability->days[0]->problems)->toBe([]);
});

it('ends the streak at a failed or expired nightly run, even if a later one closed', function () {
    stabilityStableDays('2026-10-26', 7);
    stabilityRun('2026-10-24', Company::Sgx, Dataset::Cartera, 'fallida');
    stabilityRun('2026-10-22', Company::Sdc, Dataset::Maestros, 'vencida');

    $days = stabilityDays();

    expect(app(Stability::class)->current()->stableDays)->toBe(2)
        ->and($days['2026-10-24']->nightlyRunsOk)->toBeFalse()
        ->and($days['2026-10-24']->countsMatch)->toBeTrue()
        ->and($days['2026-10-24']->problems)->toBe(['Falló la corrida nocturna de SGX CARTERA.'])
        ->and($days['2026-10-22']->problems)->toBe(['Venció la corrida nocturna de SDC MAESTROS.']);
});

it('ends the streak at a count that does not match', function () {
    stabilityStableDays('2026-10-26', 7);
    DB::table('daily_counts')->where('fecha', 'like', '2026-10-25%')->where('empresa', 'SDC')->where('parte', 'clientes')
        ->update(['sap' => 6, 'cuadra' => false]);

    $days = stabilityDays();

    expect(app(Stability::class)->current()->stableDays)->toBe(1)
        ->and($days['2026-10-25']->countsMatch)->toBeFalse()
        ->and($days['2026-10-25']->nightlyRunsOk)->toBeTrue()
        ->and($days['2026-10-25']->problems)->toBe(['No cuadra el conteo de SDC clientes.']);
});

it('ends the streak at a late, failed or expired request and ignores waiting ones', function () {
    stabilityStableDays('2026-10-26', 7);
    stabilityRequest('terminada', '2026-10-26 09:00:00', '2026-10-26 09:09:59');
    stabilityRequest('pendiente', '2026-10-26 23:58:00');
    stabilityRequest('tomada', '2026-10-26 23:50:00');
    $late = stabilityRequest('terminada', '2026-10-24 15:00:00', '2026-10-24 15:14:30');
    $failed = stabilityRequest('fallida', '2026-10-22 11:00:00', '2026-10-22 11:02:00');
    $expired = stabilityRequest('vencida', '2026-10-22 16:00:00', '2026-10-22 16:30:00');

    $days = stabilityDays();

    expect(app(Stability::class)->current()->stableDays)->toBe(2)
        ->and($days['2026-10-26']->requestsOnTime)->toBeTrue()
        ->and($days['2026-10-24']->requestsOnTime)->toBeFalse()
        ->and($days['2026-10-24']->problems)->toBe(["La solicitud {$late} tardó 14 minutos."])
        ->and($days['2026-10-22']->problems)->toBe(["La solicitud {$failed} falló.", "La solicitud {$expired} venció."]);
});

it('caps the streak at the target, also when today is still in progress', function () {
    stabilityStableDays('2026-10-27', 20);

    expect(app(Stability::class)->current()->stableDays)->toBe(Stability::TARGET_DAYS);

    DB::table('daily_counts')->where('fecha', 'like', '2026-10-27%')->delete();

    // Today is not stable yet, but the 14 days before it are.
    expect(app(Stability::class)->current()->stableDays)->toBe(Stability::TARGET_DAYS);
});
