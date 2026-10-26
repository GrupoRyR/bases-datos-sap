<?php

namespace App\Modules\Sap\Application\Apply;

use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Models\Run;
use Illuminate\Support\Facades\DB;

/**
 * Compares a full run once applied (docs/contrato-robot.md, section 4.3):
 * per part, the SAP count the robot sent, the rows received and the active
 * rows of the company in MySQL. A mismatch never fails the run; it is kept
 * in daily_counts and counts against the 14 stable days (plan, section 6).
 */
final class CountRun
{
    /**
     * @param  array<string, int>  $received
     * @param  array<string, int>  $sap
     * @return array<string, array{sap: int, recibidas: int, activas_mysql: int, cuadra: bool}>
     */
    public function compare(Run $run, array $received, array $sap): array
    {
        $counts = [];

        foreach (array_keys($run->partes) as $name) {
            $part = Part::from($name);
            $active = $this->activeRows($run, $part);

            $counts[$name] = [
                'sap' => $sap[$name],
                'recibidas' => $received[$name],
                'activas_mysql' => $active,
                'cuadra' => $sap[$name] === $received[$name] && $received[$name] === $active,
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
            ['conjunto', 'sap', 'recibidas', 'activas_mysql', 'cuadra', 'run_id', 'updated_at'],
        );

        return $counts;
    }

    /**
     * Active rows of the company; CARTERA lines have no flag, so all count.
     */
    private function activeRows(Run $run, Part $part): int
    {
        return DB::connection($part->dataset()->connection())->table($part->table())
            ->where('empresa', $run->empresa->value)
            ->when($part->dataset() === Dataset::Maestros, fn ($query) => $query->where('activo', true))
            ->count();
    }
}
