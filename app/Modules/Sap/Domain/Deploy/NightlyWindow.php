<?php

namespace App\Modules\Sap\Domain\Deploy;

use Carbon\CarbonImmutable;
use InvalidArgumentException;

/**
 * The time around the nightly run when no deploy may start, in the app
 * timezone (Bogota), as the blocked slots read theirs, so both guards move
 * together. The start is included and the end excluded, like the blocked
 * slots: with "01:45-02:15", 01:45:00 and 02:14:59 are inside and 02:15:00
 * is not. A window whose end comes before its start crosses midnight; one
 * whose start equals its end is refused, since it would turn the guard off.
 */
final readonly class NightlyWindow
{
    private function __construct(private int $start, private int $end) {}

    /**
     * @param  string  $window  "HH:MM-HH:MM", as BASES_SAP_VENTANA_NOCTURNA_DESPLIEGUE.
     *
     * @throws InvalidArgumentException When it is not two valid times, or both are the same.
     */
    public static function fromConfig(string $window): self
    {
        if (preg_match('/^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$/', str_replace(' ', '', $window), $parts) !== 1) {
            throw new InvalidArgumentException("Invalid nightly window [{$window}].");
        }

        [, $startHour, $startMinute, $endHour, $endMinute] = array_map('intval', $parts);

        if ($startHour > 23 || $endHour > 23 || $startMinute > 59 || $endMinute > 59) {
            throw new InvalidArgumentException("Invalid nightly window [{$window}].");
        }

        [$start, $end] = [$startHour * 60 + $startMinute, $endHour * 60 + $endMinute];

        if ($start === $end) {
            throw new InvalidArgumentException("Empty nightly window [{$window}].");
        }

        return new self($start, $end);
    }

    public function contains(CarbonImmutable $at): bool
    {
        $time = $at->setTimezone((string) config('app.timezone'));
        $second = $time->hour * 3600 + $time->minute * 60 + $time->second;
        [$start, $end] = [$this->start * 60, $this->end * 60];

        return $start <= $end
            ? $second >= $start && $second < $end
            : $second >= $start || $second < $end;
    }

    public function label(): string
    {
        return sprintf('%02d:%02d-%02d:%02d', intdiv($this->start, 60), $this->start % 60, intdiv($this->end, 60), $this->end % 60);
    }
}
