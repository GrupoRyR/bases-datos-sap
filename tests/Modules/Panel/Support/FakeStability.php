<?php

namespace Tests\Modules\Panel\Support;

use App\Modules\Sap\Contracts\Data\StabilityData;
use App\Modules\Sap\Contracts\Data\StabilityDayData;
use App\Modules\Sap\Contracts\Stability;
use Carbon\CarbonImmutable;

/**
 * Stability that returns a fixed counter. By default the last 14 Bogota
 * days (today first) are all stable; pass the problems of the unstable
 * days by their offset from today (0 = today). With $todayInProgress,
 * today is not stable yet but has no problems, as before the nightly run.
 */
final class FakeStability implements Stability
{
    /**
     * @param  array<int, list<string>>  $problems  Days ago => problems of that day.
     */
    public function __construct(
        private int $stableDays = self::TARGET_DAYS,
        private array $problems = [],
        private bool $todayInProgress = false,
    ) {}

    public function current(): StabilityData
    {
        $today = CarbonImmutable::now('America/Bogota')->startOfDay();
        $days = [];

        for ($ago = 0; $ago < self::TARGET_DAYS; $ago++) {
            $problems = $this->problems[$ago] ?? [];
            $stable = $problems === [] && ! ($ago === 0 && $this->todayInProgress);

            $days[] = new StabilityDayData($today->subDays($ago), $stable, $stable, $stable, $stable, $problems);
        }

        return new StabilityData($this->stableDays, self::TARGET_DAYS, $days);
    }
}
