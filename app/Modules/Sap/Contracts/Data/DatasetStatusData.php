<?php

namespace App\Modules\Sap\Contracts\Data;

use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use Carbon\CarbonImmutable;

/**
 * A dataset of a company as the panel shows it. lastAppliedAt is when the
 * newest closed run applied it (null if none yet); rows maps each part to
 * its rows of the company in MySQL (active rows when the table marks them,
 * every row otherwise); lastRun is its latest run in any state.
 */
final readonly class DatasetStatusData
{
    /**
     * @param  array<string, int>  $rows  Part value => rows.
     */
    public function __construct(
        public Company $company,
        public Dataset $dataset,
        public ?CarbonImmutable $lastAppliedAt,
        public array $rows,
        public ?RunSummaryData $lastRun,
    ) {}
}
