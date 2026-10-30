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

    /**
     * "a las 12:45" when the moment falls today in Bogota, otherwise
     * "el 30 oct a las 00:15", so a time never reads as the wrong day.
     */
    public static function at(CarbonInterface $moment): string
    {
        $local = self::bogota($moment);

        return $local->isSameDay(self::bogota(now()))
            ? 'a las '.$local->format('H:i')
            : 'el '.self::dateTime($moment);
    }

    /**
     * How long it took from $from to $to: "menos de un minuto", "4 min",
     * "1 h" or "1 h 5 min". Whole minutes, rounded down.
     */
    public static function duration(CarbonInterface $from, CarbonInterface $to): string
    {
        $minutes = intdiv(max(0, (int) $from->diffInSeconds($to)), 60);

        if ($minutes === 0) {
            return 'menos de un minuto';
        }

        $hours = intdiv($minutes, 60);
        $minutes %= 60;

        return match (true) {
            $hours === 0 => "{$minutes} min",
            $minutes === 0 => "{$hours} h",
            default => "{$hours} h {$minutes} min",
        };
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
