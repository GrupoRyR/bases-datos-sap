<?php

namespace App\Modules\Sap\Application\Apply;

use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Models\Run;
use Carbon\CarbonInterface;
use Illuminate\Support\Facades\DB;

/**
 * Applies a closed PEDIDOS run (docs/contrato-robot.md, section 11.3). The
 * caller wraps it in one transaction on the ventas connection, so the
 * company's open order lines are replaced at once and never seen empty.
 *
 * The run is a photo of what is open in SAP: every line of the company is
 * replaced, so a line invoiced or closed since the last run disappears. The
 * full run and the request runs do the same; CloseRun already refused an
 * empty run, so the previous lines stay when SAP reads nothing.
 */
final class ApplyPedidos
{
    /** Lines per insert: 39 columns stay under the placeholder limits. */
    private const CHUNK = 200;

    public function apply(Run $run, CarbonInterface $appliedAt): void
    {
        $company = $run->empresa->value;

        DB::connection('ventas')->table('pedidos')->where('empresa', $company)->delete();

        $run->rowsOf(Part::Orders)->chunk(self::CHUNK)->each(function ($lines) use ($run, $company, $appliedAt) {
            DB::connection('ventas')->table('pedidos')->insert($lines->map(fn (array $line): array => [
                'empresa' => $company,
                ...$line,
                'sincronizado_en' => $appliedAt,
                'corrida_id' => $run->id,
            ])->values()->all());
        });
    }
}
