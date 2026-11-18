<?php

namespace App\Modules\Sap\Application\Apply;

use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Models\Run;
use Illuminate\Support\Facades\DB;

/**
 * Compares a full run once applied (docs/contrato-robot.md, section 4.3):
 * per part, the SAP count the robot sent, the rows received, the received
 * rows that are active and the active rows of the company in MySQL (in a
 * part with a window, the rows of its window; in PEDIDOS and the PRODUCCION
 * masters, all of them). SAP sends the inactive rows too, so MySQL
 * is compared with the received active rows, not with all of them. A
 * mismatch never fails the run; it is kept in daily_counts and counts
 * against the 14 stable days (plan, section 6).
 */
final class CountRun
{
    /**
     * @param  array<string, int>  $received
     * @param  array<string, int>  $sap
     * @return array<string, array{sap: int, recibidas: int, activas_recibidas: int, activas_mysql: int, cuadra: bool}>
     */
    public function compare(Run $run, array $received, array $sap): array
    {
        $counts = [];

        foreach (array_keys($run->partes) as $name) {
            $part = Part::from($name);
            $activeReceived = $this->activeReceived($run, $part, $received[$name]);
            $active = $this->activeRows($run, $part);

            $counts[$name] = [
                'sap' => $sap[$name],
                'recibidas' => $received[$name],
                'activas_recibidas' => $activeReceived,
                'activas_mysql' => $active,
                'cuadra' => $sap[$name] === $received[$name] && $active === $activeReceived,
            ];
        }

        $day = $run->extraida_en->copy()->setTimezone((string) config('app.timezone'))->toDateString();
        $now = now();

        DB::table('daily_counts')->upsert(
            array_map(fn (string $name, array $count): array => [
                'fecha' => $day,
                'empresa' => $run->empresa->value,
                'conjunto' => $run->conjunto->value,
                'parte' => $name,
                ...$count,
                'run_id' => $run->id,
                'created_at' => $now,
                'updated_at' => $now,
            ], array_keys($counts), $counts),
            ['fecha', 'empresa', 'parte'],
            ['conjunto', 'sap', 'recibidas', 'activas_recibidas', 'activas_mysql', 'cuadra', 'run_id', 'updated_at'],
        );

        return $counts;
    }

    /**
     * The received rows that are active. A part without an activo column
     * (addresses, CARTERA, VENTAS, PEDIDOS, PRODUCCION) stores every received row as active, so
     * they all count.
     */
    private function activeReceived(Run $run, Part $part, int $received): int
    {
        if (! isset($part->columns()['activo'])) {
            return $received;
        }

        return $run->rowsOf($part)->filter(fn (array $row): bool => $row['activo'] === true)->count();
    }

    /**
     * Active rows of the company. Only MAESTROS has a flag; elsewhere all
     * rows count, but a part with a window (VENTAS and the PRODUCCION
     * movement) counts the rows of the run's window, which is what the SAP
     * count covers (contract sections 10.2 and 12.3).
     */
    private function activeRows(Run $run, Part $part): int
    {
        return DB::connection($part->dataset()->connection())->table($part->table())
            ->where('empresa', $run->empresa->value)
            ->when($part->dataset() === Dataset::Maestros, fn ($query) => $query->where('activo', true))
            ->when($part->windowColumn() !== null, fn ($query) => $query->where((string) $part->windowColumn(), '>=', $run->ventana_desde?->toDateString()))
            ->count();
    }
}
