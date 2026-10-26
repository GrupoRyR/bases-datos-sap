<?php

namespace App\Modules\Sap\Application\Apply;

use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Domain\Runs\RunType;
use App\Modules\Sap\Models\Run;
use Carbon\CarbonImmutable;
use Carbon\CarbonInterface;
use Illuminate\Support\Facades\DB;

/**
 * Applies a closed CARTERA run (docs/contrato-robot.md, section 6). The
 * caller wraps it in one transaction on the cartera connection, so the
 * company's receivables are replaced at once and never seen empty.
 *
 * The nightly full run also keeps the photo of its cut-off date, replacing
 * an earlier photo of the same company and day. As the query counts overdue
 * days to the day it runs, the photo counts them to the cut-off date
 * (docs/plan-bases-sap.md, section 4).
 */
final class ApplyCartera
{
    /** Lines per insert: 41 columns stay under the placeholder limits. */
    private const CHUNK = 200;

    public function apply(Run $run, CarbonInterface $appliedAt): void
    {
        $company = $run->empresa->value;
        $cutOff = $run->fecha_corte === null ? null : CarbonImmutable::parse($run->fecha_corte->toDateString());
        $photo = $run->tipo === RunType::Full && $cutOff !== null;

        DB::connection('cartera')->table('cartera')->where('empresa', $company)->delete();

        if ($photo) {
            DB::connection('cartera')->table('cartera_fotos')
                ->where('empresa', $company)->where('fecha_corte', $cutOff->toDateString())->delete();
        }

        $run->rowsOf(Part::Receivables)->chunk(self::CHUNK)->each(function ($lines) use ($run, $company, $appliedAt, $photo, $cutOff) {
            $lines = $lines->map(fn (array $line): array => [
                'empresa' => $company,
                ...$line,
                'sincronizado_en' => $appliedAt,
                'corrida_id' => $run->id,
            ])->values()->all();

            DB::connection('cartera')->table('cartera')->insert($lines);

            if ($photo) {
                DB::connection('cartera')->table('cartera_fotos')->insert(array_map(fn (array $line): array => [
                    ...$line,
                    'fecha_corte' => $cutOff->toDateString(),
                    'dias' => (int) CarbonImmutable::parse($line['fecha_vencimiento'])->diffInDays($cutOff, false),
                ], $lines));
            }
        });
    }
}
