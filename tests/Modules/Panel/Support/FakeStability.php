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
 * today is in progress, as before the nightly run: not stable, with what
 * has not run yet as its problems.
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
            $inProgress = $ago === 0 && $this->todayInProgress;
            $problems = $inProgress ? ['No hubo corrida nocturna cerrada de SGX MAESTROS.'] : ($this->problems[$ago] ?? []);
            $stable = $problems === [];

            $days[] = new StabilityDayData($today->subDays($ago), $stable, $stable, $stable, $stable, $problems, $inProgress);
        }

        return new StabilityData($this->stableDays, self::TARGET_DAYS, $days);
    }
}
