<?php

namespace App\Modules\Sap\Domain\Requests;

use Carbon\CarbonImmutable;

/**
 * The times other robots use the VPN (docs/contrato-robot.md, section 7.2,
 * rule 5). A time from margin minutes before a slot until margin minutes
 * after it is blocked and moves to the end of the window; windows that
 * touch chain, so 11:50 with 12:00 and 12:30 moves to 12:45.
 */
final readonly class BlockedSlots
{
    /**
     * @param  list<array{int, int}>  $times  Hour and minute of each slot, in the app timezone.
     */
    private function __construct(private array $times, private int $margin) {}

    /**
     * @param  string  $slots  "HH:MM" separated by commas, as BASES_SAP_FRANJAS_BLOQUEADAS.
     */
    public static function fromConfig(string $slots, int $margin): self
    {
        $times = [];

        foreach (explode(',', $slots) as $slot) {
            if (preg_match('/^(\d{1,2}):(\d{2})$/', trim($slot), $parts) === 1) {
                $times[] = [(int) $parts[1], (int) $parts[2]];
            }
        }

        return new self($times, $margin);
    }

    /**
     * The first time at or after $at that is outside every window.
     */
    public function next(CarbonImmutable $at): CarbonImmutable
    {
        $time = $at->setTimezone((string) config('app.timezone'));

        do {
            $moved = false;

            // Yesterday's and tomorrow's slots too: 23:50 falls in 00:00's window.
            foreach ([-1, 0, 1] as $days) {
                foreach ($this->times as [$hour, $minute]) {
                    $slot = $time->startOfDay()->addDays($days)->setTime($hour, $minute);

                    if ($time >= $slot->subMinutes($this->margin) && $time < $slot->addMinutes($this->margin)) {
                        $time = $slot->addMinutes($this->margin);
                        $moved = true;
                    }
                }
            }
        } while ($moved);

        return $time;
    }
}
