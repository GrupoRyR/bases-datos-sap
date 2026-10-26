<?php

namespace App\Modules\Sap\Domain\Values;

use Carbon\CarbonImmutable;
use Throwable;

/**
 * Dates and times as the robot sends them (docs/contrato-robot.md,
 * section 2): dates "YYYY-MM-DD" and times ISO 8601 with an offset.
 * Times are kept in the app timezone (America/Bogota).
 */
final class SapTime
{
    private const DATE = '/^(\d{4})-(\d{2})-(\d{2})$/';

    private const DATE_TIME = '/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})$/';

    /**
     * Whether the value is a real calendar date "YYYY-MM-DD".
     */
    public static function isDate(mixed $value): bool
    {
        return is_string($value)
            && preg_match(self::DATE, $value, $parts) === 1
            && checkdate((int) $parts[2], (int) $parts[3], (int) $parts[1]);
    }

    /**
     * The time in the app timezone, or null if it is not ISO 8601 with an
     * offset (a time without one is ambiguous).
     */
    public static function parse(mixed $value): ?CarbonImmutable
    {
        if (! is_string($value) || preg_match(self::DATE_TIME, $value) !== 1 || ! self::isDate(substr($value, 0, 10))) {
            return null;
        }

        try {
            return CarbonImmutable::parse($value)->setTimezone((string) config('app.timezone'));
        } catch (Throwable) {
            return null;
        }
    }
}
