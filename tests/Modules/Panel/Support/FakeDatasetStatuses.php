<?php

namespace Tests\Modules\Panel\Support;

use App\Modules\Sap\Contracts\Data\DatasetStatusData;
use App\Modules\Sap\Contracts\Data\RunSummaryData;
use App\Modules\Sap\Contracts\DatasetStatuses;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use Carbon\CarbonImmutable;

/**
 * DatasetStatuses that returns the statuses it was given, so panel tests
 * never touch the Sap tables.
 */
final class FakeDatasetStatuses implements DatasetStatuses
{
    /**
     * @param  list<DatasetStatusData>  $statuses
     */
    public function __construct(private array $statuses = []) {}

    public function all(): array
    {
        return $this->statuses;
    }

    /**
     * A status with sensible defaults: applied today at 02:15 Bogota with a
     * closed nightly run, unless the caller overrides it.
     *
     * @param  array<string, int>  $rows
     */
    public static function status(
        Company $company = Company::Sgx,
        Dataset $dataset = Dataset::Maestros,
        ?CarbonImmutable $lastAppliedAt = null,
        array $rows = ['clientes' => 1200],
        ?RunSummaryData $lastRun = null,
    ): DatasetStatusData {
        return new DatasetStatusData($company, $dataset, $lastAppliedAt, $rows, $lastRun);
    }

    public static function run(
        string $state = 'cerrada',
        string $type = 'completa',
        ?string $error = null,
        string $startedAt = '2026-10-29 02:00',
        ?string $finishedAt = '2026-10-29 02:15',
    ): RunSummaryData {
        return new RunSummaryData(
            id: 7,
            type: $type,
            state: $state,
            startedAt: CarbonImmutable::parse($startedAt, 'America/Bogota'),
            finishedAt: $finishedAt === null ? null : CarbonImmutable::parse($finishedAt, 'America/Bogota'),
            error: $error,
        );
    }
}
