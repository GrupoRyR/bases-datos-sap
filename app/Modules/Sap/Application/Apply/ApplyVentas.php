<?php

namespace App\Modules\Sap\Application\Apply;

use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Models\Run;
use Carbon\CarbonInterface;
use Illuminate\Support\Facades\DB;
use LogicException;

/**
 * Applies a closed VENTAS run (docs/contrato-robot.md, section 10.2). The
 * caller wraps it in one transaction on the ventas connection, so the
 * company's window is replaced at once and never seen empty.
 *
 * Only the lines posted (fecha_contabilizacion) from the run's window on are
 * replaced: a line of the window that no longer comes from SAP disappears,
 * and nothing earlier is ever touched. That is the frozen history
 * Comisiones reads (docs/plan-bases-sap.md, section 4). The batches already
 * refused any line before the window, so every received line lands in it.
 */
final class ApplyVentas
{
    /** Lines per insert: 37 columns stay under the placeholder limits. */
    private const CHUNK = 200;

    public function apply(Run $run, CarbonInterface $appliedAt): void
    {
        $company = $run->empresa->value;
        $from = $run->ventana_desde?->toDateString()
            ?? throw new LogicException("VENTAS run {$run->id} has no window.");

        DB::connection('ventas')->table('ventas')
            ->where('empresa', $company)
            ->where('fecha_contabilizacion', '>=', $from)
            ->delete();

        $run->rowsOf(Part::Sales)->chunk(self::CHUNK)->each(function ($lines) use ($run, $company, $appliedAt) {
            DB::connection('ventas')->table('ventas')->insert($lines->map(fn (array $line): array => [
                'empresa' => $company,
                ...$line,
                'sincronizado_en' => $appliedAt,
                'corrida_id' => $run->id,
            ])->values()->all());
        });
    }
}
