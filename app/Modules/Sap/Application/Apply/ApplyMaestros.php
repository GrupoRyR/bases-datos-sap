<?php

namespace App\Modules\Sap\Application\Apply;

use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Domain\Runs\PartMode;
use App\Modules\Sap\Models\Run;
use Carbon\CarbonInterface;
use Illuminate\Database\Query\Builder;
use Illuminate\Support\Facades\DB;

/**
 * Applies a closed MAESTROS run (docs/contrato-robot.md, sections 4.3 and
 * 5.1). The caller wraps it in one transaction on the maestros connection.
 *
 * - Every row is inserted or updated by company and key, and stamped with
 *   sincronizado_en and the run.
 * - A part in "todo" inactivates the company's rows the run did not bring.
 * - Addresses and contacts of every partner sent are refreshed whole, in any
 *   mode: the ones the run did not bring for that partner become inactive.
 *
 * Rows are never deleted.
 */
final class ApplyMaestros
{
    /** Rows per statement: well under the placeholder limits of MySQL and SQLite. */
    private const CHUNK = 200;

    public function apply(Run $run, CarbonInterface $appliedAt): void
    {
        $partners = [];

        foreach ($run->partes as $name => $mode) {
            $part = Part::from($name);

            $run->rowsOf($part)->chunk(self::CHUNK)->each(function ($rows) use ($run, $part, $appliedAt, &$partners) {
                $rows = $rows->map(fn (array $row): array => $this->stamp($row, $run, $appliedAt))->values()->all();

                if (in_array($part, [Part::Customers, Part::Suppliers], true)) {
                    array_push($partners, ...array_column($rows, 'codigo'));
                }

                $this->table($part)->upsert(
                    $rows,
                    ['empresa', ...$part->key()],
                    array_values(array_diff(array_keys($rows[0]), ['empresa', ...$part->key()])),
                );
            });

            if ($mode === PartMode::Full->value) {
                $this->inactivateAbsent($part, $run, $appliedAt);
            }
        }

        foreach ([Part::Addresses, Part::Contacts] as $part) {
            if (array_key_exists($part->value, $run->partes)) {
                foreach (array_chunk(array_unique($partners), self::CHUNK) as $chunk) {
                    $this->inactivateAbsent($part, $run, $appliedAt, fn (Builder $query) => $query->whereIn('codigo_socio', $chunk));
                }
            }
        }
    }

    /**
     * The row as stored: company, run and sync time; parts without a flag
     * of their own (addresses) come in as active.
     *
     * @param  array<string, mixed>  $row
     * @return array<string, mixed>
     */
    private function stamp(array $row, Run $run, CarbonInterface $appliedAt): array
    {
        return [
            'empresa' => $run->empresa->value,
            ...$row,
            'activo' => $row['activo'] ?? true,
            'sincronizado_en' => $appliedAt,
            'corrida_id' => $run->id,
        ];
    }

    /**
     * Marks inactive the active rows of the company (optionally narrowed)
     * that this run did not write.
     */
    private function inactivateAbsent(Part $part, Run $run, CarbonInterface $appliedAt, ?callable $narrow = null): void
    {
        $this->table($part)
            ->where('empresa', $run->empresa->value)
            ->where('activo', true)
            ->where(fn (Builder $query) => $query->whereNull('corrida_id')->orWhere('corrida_id', '<>', $run->id))
            ->when($narrow, $narrow)
            ->update(['activo' => false, 'sincronizado_en' => $appliedAt, 'corrida_id' => $run->id]);
    }

    private function table(Part $part): Builder
    {
        return DB::connection('maestros')->table($part->table());
    }
}
