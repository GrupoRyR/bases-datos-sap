<?php

namespace App\Modules\Sap\Application\Panel;

use App\Modules\Sap\Application\Totals\TotalsScope;
use App\Modules\Sap\Contracts\Comparisons;
use App\Modules\Sap\Contracts\Data\ComparisonData;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Models\RobotComparison;
use Carbon\CarbonImmutable;

/**
 * Reads the latest comparison of each company and dataset from
 * robot_comparisons, one indexed query per pair.
 */
final class DatabaseComparisons implements Comparisons
{
    public function latest(): array
    {
        $latest = [];

        foreach (Company::cases() as $company) {
            foreach (TotalsScope::DATASETS as $dataset) {
                $comparison = RobotComparison::query()
                    ->where('conjunto', $dataset->value)
                    ->where('empresa', $company->value)
                    ->orderByDesc('comparada_en')
                    ->orderByDesc('id')
                    ->first();

                if ($comparison !== null) {
                    $latest[] = new ComparisonData(
                        id: $comparison->id,
                        company: $comparison->empresa,
                        dataset: $comparison->conjunto,
                        from: $comparison->desde?->toDateString(),
                        until: $comparison->hasta?->toDateString(),
                        matches: $comparison->cuadra,
                        differences: $comparison->diferencias,
                        comparedAt: CarbonImmutable::instance($comparison->comparada_en),
                        receivedAt: CarbonImmutable::instance($comparison->created_at),
                    );
                }
            }
        }

        return $latest;
    }
}
