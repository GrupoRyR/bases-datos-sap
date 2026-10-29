<?php

namespace App\Modules\Panel\Support;

use Illuminate\Support\Facades\Lang;

/**
 * Spanish labels of the Sap values the panel shows, from
 * resources/lang/es/etiquetas.php. A value without a label (say a new
 * VENTAS dataset) shows as is, so the panel never needs a change to list
 * what Sap adds.
 */
final class Labels
{
    public static function company(string $value): string
    {
        return self::of('empresas', $value);
    }

    public static function dataset(string $value): string
    {
        return self::of('conjuntos', $value);
    }

    public static function part(string $value): string
    {
        return self::of('partes', $value);
    }

    /** "completa" or "solicitud". */
    public static function runType(string $value): string
    {
        return self::of('tipos_corrida', $value);
    }

    /** "abierta", "cerrada", "fallida" or "vencida". */
    public static function runState(string $value): string
    {
        return self::of('estados_corrida', $value);
    }

    /**
     * The badge tone of a run state; unknown states stay neutral.
     */
    public static function runStateTone(string $state): string
    {
        return match ($state) {
            'cerrada' => 'success',
            'fallida' => 'danger',
            'vencida' => 'warning',
            'abierta' => 'info',
            default => 'neutral',
        };
    }

    /**
     * The label of $value in a group of etiquetas.php, or $value itself.
     */
    public static function of(string $group, string $value): string
    {
        $key = "panel::etiquetas.{$group}.{$value}";

        if ($value === '' || ! Lang::has($key)) {
            return $value;
        }

        $label = Lang::get($key);

        return is_string($label) ? $label : $value;
    }
}
