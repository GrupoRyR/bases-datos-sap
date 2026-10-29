<?php

namespace App\Modules\Sap\Application\Panel;

use App\Modules\Sap\Contracts\Data\DatasetStatusData;
use App\Modules\Sap\Contracts\Data\RunSummaryData;
use App\Modules\Sap\Contracts\DatasetStatuses;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Domain\Runs\RunState;
use App\Modules\Sap\Models\Run;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/**
 * Reads the status of every dataset in a fixed number of queries, whatever
 * the number of companies: one for the last applied times, one for the
 * latest runs and, per part, a column check and one grouped count.
 */
final class DatabaseDatasetStatuses implements DatasetStatuses
{
    public function all(): array
    {
        $applied = DB::table('robot_runs')
            ->where('estado', RunState::Closed->value)
            ->groupBy('empresa', 'conjunto')
            ->selectRaw('empresa, conjunto, MAX(aplicada_en) AS aplicada_en')
            ->get()
            ->mapWithKeys(fn (object $row): array => ["{$row->empresa}:{$row->conjunto}" => $row->aplicada_en]);

        $lastRuns = Run::query()
            ->whereIn('id', DB::table('robot_runs')->groupBy('empresa', 'conjunto')->selectRaw('MAX(id)'))
            ->get()
            ->keyBy(fn (Run $run): string => "{$run->empresa->value}:{$run->conjunto->value}");

        $rows = $this->rows();
        $statuses = [];

        foreach (Company::cases() as $company) {
            foreach (Dataset::cases() as $dataset) {
                $key = "{$company->value}:{$dataset->value}";
                $appliedAt = $applied->get($key);
                $run = $lastRuns->get($key);

                $statuses[] = new DatasetStatusData(
                    company: $company,
                    dataset: $dataset,
                    lastAppliedAt: $appliedAt === null ? null : CarbonImmutable::parse($appliedAt, (string) config('app.timezone')),
                    rows: array_map(fn (array $byCompany): int => $byCompany[$company->value] ?? 0, $rows[$dataset->value]),
                    lastRun: $run === null ? null : new RunSummaryData(
                        id: $run->id,
                        type: $run->tipo->value,
                        state: $run->estado->value,
                        startedAt: CarbonImmutable::instance($run->created_at),
                        finishedAt: $run->terminada_en?->toImmutable(),
                        error: $run->error,
                    ),
                );
            }
        }

        return $statuses;
    }

    /**
     * Rows per dataset, part and company. Like the nightly count (CountRun),
     * a table that marks rows activo counts only the active ones.
     *
     * @return array<string, array<string, array<string, int>>>
     */
    private function rows(): array
    {
        $rows = [];

        foreach (Dataset::cases() as $dataset) {
            $rows[$dataset->value] = [];

            foreach (Part::forDataset($dataset) as $part) {
                $connection = $dataset->connection();

                $rows[$dataset->value][$part->value] = DB::connection($connection)->table($part->table())
                    ->when(Schema::connection($connection)->hasColumn($part->table(), 'activo'), fn ($query) => $query->where('activo', true))
                    ->groupBy('empresa')
                    ->selectRaw('empresa, COUNT(*) AS filas')
                    ->pluck('filas', 'empresa')
                    ->map(fn (mixed $count): int => (int) $count)
                    ->all();
            }
        }

        return $rows;
    }
}
