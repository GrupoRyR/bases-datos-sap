<?php

namespace App\Modules\Sap\Application\Runs;

use App\Modules\Sap\Application\Apply\ApplyCartera;
use App\Modules\Sap\Application\Apply\ApplyMaestros;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Domain\Runs\PartMode;
use App\Modules\Sap\Domain\Runs\RunState;
use App\Modules\Sap\Domain\Runs\RunType;
use App\Modules\Sap\Http\Exceptions\RobotRequestRejected;
use App\Modules\Sap\Models\Run;
use Illuminate\Support\Facades\DB;

/**
 * Closes a run and applies it (docs/contrato-robot.md, section 4.3): checks
 * that every declared batch and row arrived, then writes the dataset in
 * one transaction and records what was applied. Until this commits the
 * apps keep seeing the previous data; if anything fails, nothing changes.
 */
final class CloseRun
{
    public function __construct(
        private readonly OpenRuns $runs,
        private readonly ApplyMaestros $maestros,
        private readonly ApplyCartera $cartera,
    ) {}

    /**
     * @param  array<string, mixed>  $input
     */
    public function handle(int $runId, array $input): Run
    {
        $run = $this->runs->find($runId);
        [$batches, $declared, $sapCounts] = $this->validated($run, $input);

        $appliedAt = now();

        // Under a lock on the run, so a late batch, its expiry or a second
        // close cannot change what is counted and applied. Returns the full
        // parts that came empty instead of applying anything.
        $empty = DB::transaction(function () use ($run, $appliedAt, $batches, $declared, $sapCounts): array {
            $current = Run::query()->whereKey($run->id)->lockForUpdate()->firstOrFail();

            if ($current->estado !== RunState::Open) {
                throw new RobotRequestRejected(409, 'La corrida ya no está abierta.', ['estado' => $current->estado->value]);
            }

            $rows = $this->checkReceived($run, $batches, $declared);
            $empty = array_keys(array_filter($rows, fn (int $count, string $part): bool => $count === 0 && $run->partes[$part] === PartMode::Full->value, ARRAY_FILTER_USE_BOTH));

            if ($empty !== []) {
                return $empty;
            }

            DB::connection($run->conjunto->connection())->transaction(fn () => $run->conjunto === Dataset::Maestros
                ? $this->maestros->apply($run, $appliedAt)
                : $this->cartera->apply($run, $appliedAt));

            $run->finish(RunState::Closed, null, [
                'batches' => $batches,
                'filas' => $rows,
                'conteo_sap' => $sapCounts,
                'aplicada_en' => $appliedAt,
            ]);

            return [];
        });

        if ($empty !== []) {
            $this->failEmpty($run, $empty);
        }

        return $run;
    }

    /**
     * The rows received per part, once every declared batch is there and the
     * rows match what the robot declared; 409 otherwise, and the run stays open.
     *
     * @param  array<string, int>  $declared
     * @return array<string, int>
     */
    private function checkReceived(Run $run, int $batches, array $declared): array
    {
        $received = DB::table('robot_batches')->where('run_id', $run->id)->pluck('parte', 'batch')->all();
        $missing = array_values(array_diff($batches > 0 ? range(1, $batches) : [], array_keys($received)));

        if ($missing !== [] || count($received) !== $batches) {
            throw new RobotRequestRejected(409, $missing !== [] ? 'Faltan lotes.' : 'Llegaron más lotes de los declarados.', ['faltan' => $missing]);
        }

        $rows = $this->receivedRows($run);

        if ($rows != $declared) {
            throw new RobotRequestRejected(409, 'Las filas no cuadran con los lotes recibidos.', ['faltan' => [], 'filas' => $rows]);
        }

        return $rows;
    }

    /**
     * @param  array<string, mixed>  $input
     * @return array{0: int, 1: array<string, int>, 2: array<string, int>|null}
     */
    private function validated(Run $run, array $input): array
    {
        $errors = [];
        $batches = $input['batches'] ?? null;

        if (! is_int($batches) || $batches < 0) {
            $errors['batches'] = 'Debe ser un entero desde 0.';
        }

        $declared = $this->counts($run, $input['filas'] ?? null, 'filas', $errors);
        $sapCounts = null;

        if ($run->tipo === RunType::Full) {
            $sapCounts = $this->counts($run, $input['conteo_sap'] ?? null, 'conteo_sap', $errors);
        } elseif (($input['conteo_sap'] ?? null) !== null) {
            $errors['conteo_sap'] = 'Solo una corrida completa envía el conteo de SAP.';
        }

        if ($errors !== []) {
            throw RobotRequestRejected::invalid('El cierre no cumple el contrato.', $errors);
        }

        /** @var int $batches */
        return [$batches, $declared, $sapCounts];
    }

    /**
     * Rows per part, exactly the parts of the run.
     *
     * @param  array<string, string>  $errors
     * @return array<string, int>
     */
    private function counts(Run $run, mixed $counts, string $field, array &$errors): array
    {
        if (! is_array($counts) || array_diff_key($run->partes, $counts) !== [] || array_diff_key($counts, $run->partes) !== []) {
            $errors[$field] = 'Debe traer un número por cada parte de la corrida.';

            return [];
        }

        foreach ($counts as $part => $count) {
            if (! is_int($count) || $count < 0) {
                $errors["{$field}.{$part}"] = 'Debe ser un entero desde 0.';
            }
        }

        return $counts;
    }

    /**
     * @return array<string, int>
     */
    private function receivedRows(Run $run): array
    {
        $received = DB::table('robot_batches')->where('run_id', $run->id)
            ->selectRaw('parte, SUM(rows_count) AS filas')->groupBy('parte')
            ->pluck('filas', 'parte')->map(fn (mixed $rows): int => (int) $rows)->all();

        return array_map(fn (string $part): int => $received[$part] ?? 0, array_combine(array_keys($run->partes), array_keys($run->partes)));
    }

    /**
     * An empty read of SAP never empties a table: a part in "todo" with no
     * rows fails the run (422) and the previous data stays.
     *
     * @param  list<string>  $empty
     */
    private function failEmpty(Run $run, array $empty): never
    {
        $run->finish(RunState::Failed, 'Llegó vacía en modo todo: '.implode(', ', $empty).'.');

        throw RobotRequestRejected::invalid('Una parte en modo todo llegó sin filas; la corrida falló y los datos anteriores siguen.', array_combine(
            array_map(fn (string $part): string => "filas.{$part}", $empty),
            array_fill(0, count($empty), 'Llegó sin filas en modo todo.'),
        ));
    }
}
