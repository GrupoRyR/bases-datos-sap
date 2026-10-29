<?php

namespace App\Modules\Sap\Contracts\Data;

/**
 * The stability counter: stable days in a row (at most targetDays) and the
 * last targetDays Bogota days, today first. Today counts once it is stable;
 * until then it does not break the streak, because it is still in progress.
 */
final readonly class StabilityData
{
    /**
     * @param  list<StabilityDayData>  $days
     */
    public function __construct(
        public int $stableDays,
        public int $targetDays,
        public array $days,
    ) {}
}
