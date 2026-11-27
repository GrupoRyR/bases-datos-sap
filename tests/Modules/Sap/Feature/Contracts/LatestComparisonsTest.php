<?php

use App\Modules\Sap\Contracts\Comparisons;
use App\Modules\Sap\Contracts\Data\ComparisonData;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Models\RobotComparison;
use Illuminate\Support\Carbon;

/*
| The panel reads the robot's comparisons with SAP (docs/contrato-robot.md,
| section 13.3) through Contracts\Comparisons: the latest one of each
| dataset and company.
*/

beforeEach(function () {
    Carbon::setTestNow(Carbon::parse('2026-11-27 04:00:00', 'America/Bogota'));
});

/**
 * @param  list<array{clave: string, campo: string, sap: string|null, mysql: string|null}>  $differences
 */
function comparisonStored(string $dataset, string $company, string $comparedAt, array $differences = []): int
{
    return RobotComparison::forceCreate([
        'conjunto' => $dataset, 'empresa' => $company, 'desde' => $dataset === 'VENTAS' ? '2025-01-01' : null,
        'hasta' => null, 'cuadra' => $differences === [], 'diferencias' => $differences,
        'comparada_en' => Carbon::parse($comparedAt), 'robot_key' => 'r2026a',
    ])->id;
}

it('answers nothing when the robot has not compared yet', function () {
    expect(app(Comparisons::class)->latest())->toBe([]);
});

it('answers the latest comparison of each dataset and company, in company then dataset order', function () {
    comparisonStored('VENTAS', 'SGX', '2026-11-26T03:00:00-05:00');
    $latestSales = comparisonStored('VENTAS', 'SGX', '2026-11-27T03:00:00-05:00', [
        ['clave' => '2026-10', 'campo' => 'filas', 'sap' => '10', 'mysql' => '9'],
    ]);
    // Sent later but compared earlier: it is not the latest.
    comparisonStored('VENTAS', 'SGX', '2026-11-25T03:00:00-05:00');
    $receivables = comparisonStored('CARTERA', 'SDC', '2026-11-27T02:30:00-05:00');
    $masters = comparisonStored('MAESTROS', 'SGX', '2026-11-27T02:00:00-05:00');

    $latest = app(Comparisons::class)->latest();

    expect(array_map(fn (ComparisonData $comparison): array => [$comparison->company, $comparison->dataset, $comparison->id], $latest))->toBe([
        [Company::Sgx, Dataset::Maestros, $masters],
        [Company::Sgx, Dataset::Ventas, $latestSales],
        [Company::Sdc, Dataset::Cartera, $receivables],
    ]);

    $sales = $latest[1];

    expect($sales->matches)->toBeFalse()
        ->and($sales->from)->toBe('2025-01-01')
        ->and($sales->until)->toBeNull()
        ->and($sales->differences)->toBe([['clave' => '2026-10', 'campo' => 'filas', 'sap' => '10', 'mysql' => '9']])
        ->and($sales->comparedAt->toIso8601String())->toBe('2026-11-27T03:00:00-05:00')
        ->and($sales->receivedAt->equalTo(now()))->toBeTrue();
});

it('breaks a tie on the comparison time by the newest one received', function () {
    comparisonStored('CARTERA', 'SGX', '2026-11-27T03:00:00-05:00');
    $newest = comparisonStored('CARTERA', 'SGX', '2026-11-27T03:00:00-05:00');

    expect(app(Comparisons::class)->latest()[0]->id)->toBe($newest);
});
