<?php

namespace App\Modules\Sap\Application\Apply;

use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Models\Run;
use Illuminate\Database\Query\Builder;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\LazyCollection;
use LogicException;

/**
 * Applies a closed complemento run (docs/contrato-robot.md, section 10.5):
 * it writes only the kilos and codigo_envio of the company's VENTAS lines of
 * the range, by key. It inserts and deletes nothing and touches no other
 * column, not even sincronizado_en nor corrida_id, so the frozen history
 * Comisiones reads keeps every value it had. The caller first checks that
 * the received lines are exactly the stored ones (unmatched) and wraps the
 * update in one transaction on the ventas connection; the open run lock
 * keeps every other VENTAS run of the company out meanwhile, so the stored
 * lines cannot change in between.
 */
final class ApplyComplemento
{
    /** The columns the run fills, each set by its own CASE on the line key. */
    private const FILLED = ['kilos', 'codigo_envio'];

    /**
     * Lines per update: four placeholders per line in each of the two CASEs
     * plus up to one doc_entry each keeps a statement near 1,800 placeholders,
     * well under the SQLite (32,766) and MySQL (65,535) limits.
     */
    private const CHUNK = 200;

    /**
     * How many received lines are not stored for the company in the range
     * (sobran) and how many stored lines of the range did not arrive (faltan).
     * Keys never repeat within a run, so each stored key is crossed off once.
     *
     * @return array{sobran: int, faltan: int}
     */
    public function unmatched(Run $run): array
    {
        $stored = [];

        foreach ($this->lines($run)->select(['tipo_objeto', 'doc_entry', 'linea'])->cursor() as $line) {
            $stored[self::key((array) $line)] = true;
        }

        $extra = 0;

        foreach ($run->rowsOf(Part::Sales) as $line) {
            $key = self::key($line);

            if (isset($stored[$key])) {
                unset($stored[$key]);
            } else {
                $extra++;
            }
        }

        return ['sobran' => $extra, 'faltan' => count($stored)];
    }

    public function apply(Run $run): void
    {
        $connection = DB::connection(Dataset::Ventas->connection());
        $table = $connection->getQueryGrammar()->wrapTable(Part::Sales->table());
        [$from, $until] = $this->range($run);

        $run->rowsOf(Part::Sales)->chunk(self::CHUNK)->each(function (LazyCollection $lines) use ($connection, $table, $run, $from, $until): void {
            $sets = [];
            $bindings = [];

            foreach (self::FILLED as $column) {
                $cases = [];

                foreach ($lines as $line) {
                    $cases[] = 'WHEN tipo_objeto = ? AND doc_entry = ? AND linea = ? THEN ?';
                    array_push($bindings, $line['tipo_objeto'], $line['doc_entry'], $line['linea'], $line[$column]);
                }

                $sets[] = "{$column} = CASE ".implode(' ', $cases)." ELSE {$column} END";
            }

            $entries = array_values(array_unique($lines->pluck('doc_entry')->all()));

            $connection->update(
                "UPDATE {$table} SET ".implode(', ', $sets)
                .' WHERE empresa = ? AND fecha_contabilizacion BETWEEN ? AND ?'
                .' AND doc_entry IN ('.implode(', ', array_fill(0, count($entries), '?')).')',
                [...$bindings, $run->empresa->value, $from, $until, ...$entries],
            );
        });
    }

    /** The company's stored lines of the run's range. */
    private function lines(Run $run): Builder
    {
        return DB::connection(Dataset::Ventas->connection())->table(Part::Sales->table())
            ->where('empresa', $run->empresa->value)
            ->whereBetween('fecha_contabilizacion', $this->range($run));
    }

    /**
     * @return array{0: string, 1: string}
     */
    private function range(Run $run): array
    {
        return [
            $run->ventana_desde?->toDateString() ?? throw new LogicException("Complemento run {$run->id} has no ventana_desde."),
            $run->ventana_hasta?->toDateString() ?? throw new LogicException("Complemento run {$run->id} has no ventana_hasta."),
        ];
    }

    /**
     * @param  array<string, mixed>  $line
     */
    private static function key(array $line): string
    {
        return implode(':', array_map(fn (mixed $value): int => (int) $value, [$line['tipo_objeto'], $line['doc_entry'], $line['linea']]));
    }
}
