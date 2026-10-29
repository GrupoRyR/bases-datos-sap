<?php

namespace App\Modules\Panel\Support;

use Carbon\CarbonInterface;

/**
 * Numbers and times as the panel shows them: Colombian thousands (dots) and
 * Bogota time in Spanish ("29 oct a las 02:15"). Carbon's own Spanish month
 * names are used, so it needs no intl extension on the server.
 */
final class Formats
{
    public const TIMEZONE = 'America/Bogota';

    public static function number(int $value): string
    {
        return number_format($value, 0, ',', '.');
    }

    /** "29 oct a las 02:15". */
    public static function dateTime(CarbonInterface $moment): string
    {
        return self::shortDate($moment).' a las '.self::bogota($moment)->format('H:i');
    }

    /** "29 oct". */
    public static function shortDate(CarbonInterface $moment): string
    {
        $moment = self::bogota($moment);

        return $moment->day.' '.rtrim($moment->locale('es')->translatedFormat('M'), '.');
    }

    /** For <time datetime>: "2026-10-29". */
    public static function isoDate(CarbonInterface $moment): string
    {
        return self::bogota($moment)->format('Y-m-d');
    }

    /** For <time datetime>: "2026-10-29T02:15:00-05:00". */
    public static function isoDateTime(CarbonInterface $moment): string
    {
        return self::bogota($moment)->toIso8601String();
    }

    private static function bogota(CarbonInterface $moment): CarbonInterface
    {
        return $moment->toImmutable()->setTimezone(self::TIMEZONE);
    }
}
