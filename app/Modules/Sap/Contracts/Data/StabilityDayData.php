<?php

namespace App\Modules\Sap\Contracts\Data;

use Carbon\CarbonImmutable;

/**
 * One Bogota day of the stability counter (date at 00:00) with the three
 * measurable criteria of the plan (section 6) and, in Spanish, what failed.
 * inProgress is true only for today while it is not stable yet but nothing
 * has gone wrong for good: it neither counts nor ends the streak.
 */
final readonly class StabilityDayData
{
    /**
     * @param  list<string>  $problems
     */
    public function __construct(
        public CarbonImmutable $date,
        public bool $nightlyRunsOk,
        public bool $countsMatch,
        public bool $requestsOnTime,
        public bool $stable,
        public array $problems,
        public bool $inProgress = false,
    ) {}
}
