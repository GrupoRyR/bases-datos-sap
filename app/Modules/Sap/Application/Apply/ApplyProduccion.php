<?php

namespace App\Modules\Sap\Application\Apply;

use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Models\Run;
use Carbon\CarbonInterface;
use Illuminate\Support\Facades\DB;
use LogicException;

/**
 * Applies a closed PRODUCCION run (docs/contrato-robot.md, section 12.3).
 * The caller wraps it in one transaction on the ventas connection, so every
 * part changes at once and is never seen empty.
 *
 * A movement part (one with a window column) replaces only the company's
 * rows dated from the run's window on; nothing earlier is touched, and the
 * batches already refused any row before the window. A master part replaces
 * every row of the company.
 */
final class ApplyProduccion
{
    /** Rows per insert: 17 columns at most stay under the placeholder limits. */
    private const CHUNK = 200;

    public function apply(Run $run, CarbonInterface $appliedAt): void
    {
        $company = $run->empresa->value;

        foreach (array_keys($run->partes) as $name) {
            $part = Part::from($name);
            $table = DB::connection('ventas')->table($part->table());
            $date = $part->windowColumn();

            $table->where('empresa', $company)
                ->when($date !== null, fn ($query) => $query->where($date, '>=', $run->ventana_desde?->toDateString()
                    ?? throw new LogicException("PRODUCCION run {$run->id} has no window.")))
                ->delete();

            $run->rowsOf($part)->chunk(self::CHUNK)->each(function ($rows) use ($run, $part, $company, $appliedAt) {
                DB::connection('ventas')->table($part->table())->insert($rows->map(fn (array $row): array => [
                    'empresa' => $company,
                    ...$row,
                    'sincronizado_en' => $appliedAt,
                    'corrida_id' => $run->id,
                ])->values()->all());
            });
        }
    }
}
