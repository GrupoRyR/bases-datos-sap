<?php

namespace App\Modules\Sap\Application\Runs;

use App\Modules\Sap\Application\Apply\ApplyCartera;
use App\Modules\Sap\Application\Apply\ApplyComplemento;
use App\Modules\Sap\Application\Apply\ApplyMaestros;
use App\Modules\Sap\Application\Apply\ApplyPedidos;
use App\Modules\Sap\Application\Apply\ApplyProduccion;
use App\Modules\Sap\Application\Apply\ApplyVentas;
use App\Modules\Sap\Application\Apply\CountRun;
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
 * A complemento run (section 10.5) only writes kilos and codigo_envio, and
 * only when its lines are exactly the company's stored lines of the range.
 */
final class CloseRun
{
    public function __construct(
        private readonly OpenRuns $runs,
        private readonly ApplyMaestros $maestros,
        private readonly ApplyCartera $cartera,
        private readonly ApplyVentas $ventas,
        private readonly ApplyPedidos $pedidos,
        private readonly ApplyProduccion $produccion,
        private readonly ApplyComplemento $complemento,
        private readonly CountRun $counts,
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
        // parts that came empty, the parts of a historical or complemento run
        // whose SAP count differs, or the lines of a complemento run that do
        // not match MySQL, instead of applying anything.
        [$empty, $mismatched, $unmatched] = DB::transaction(function () use ($run, $appliedAt, $batches, $declared, $sapCounts): array {
            $current = Run::query()->whereKey($run->id)->lockForUpdate()->firstOrFail();

            if ($current->estado !== RunState::Open) {
                throw new RobotRequestRejected(409, 'La corrida ya no está abierta.', ['estado' => $current->estado->value]);
            }

            $rows = $this->checkReceived($run, $batches, $declared);
            $empty = array_keys(array_filter($rows, fn (int $count, string $part): bool => $count === 0 && $run->partes[$part] === PartMode::Full->value, ARRAY_FILTER_USE_BOTH));

            if ($empty !== []) {
                return [$empty, [], null];
            }

            // A historical month is loaded once (contract section 10.4): one
            // that does not match SAP is never applied, since it could not be
            // loaded again. Neither is a complemento month (section 10.5),
            // which would leave lines without their weight or shipping code.
            $mismatched = $run->tipo->isPastMonth()
                ? array_keys(array_filter($rows, fn (int $count, string $part): bool => $count !== ($sapCounts[$part] ?? null), ARRAY_FILTER_USE_BOTH))
                : [];

            if ($mismatched !== []) {
                return [[], $mismatched, null];
            }

            $unmatched = $run->tipo === RunType::Complement ? $this->complemento->unmatched($run) : null;

            if ($unmatched !== null && ($unmatched['sobran'] > 0 || $unmatched['faltan'] > 0)) {
                return [[], [], $unmatched];
            }

            DB::connection($run->conjunto->connection())->transaction(fn () => match ($run->conjunto) {
                Dataset::Maestros => $this->maestros->apply($run, $appliedAt),
                Dataset::Cartera => $this->cartera->apply($run, $appliedAt),
                Dataset::Ventas => $run->tipo === RunType::Complement ? $this->complemento->apply($run) : $this->ventas->apply($run, $appliedAt),
                Dataset::Pedidos => $this->pedidos->apply($run, $appliedAt),
                Dataset::Produccion => $this->produccion->apply($run, $appliedAt),
            });

            $run->finish(RunState::Closed, null, [
                'batches' => $batches,
                'filas' => $rows,
                'conteo_sap' => $sapCounts,
                'conteo' => $sapCounts === null ? null : $this->counts->compare($run, $rows, $sapCounts),
                'aplicada_en' => $appliedAt,
            ]);

            return [[], [], null];
        });

        if ($empty !== []) {
            $this->failEmpty($run, $empty);
        }

        if ($mismatched !== []) {
            $this->failMismatched($run, $mismatched, $declared, $sapCounts ?? []);
        }

        if ($unmatched !== null) {
            $this->failUnmatched($run, $unmatched);
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

        if ($run->tipo->isWhole()) {
            $sapCounts = $this->counts($run, $input['conteo_sap'] ?? null, 'conteo_sap', $errors);
        } elseif (($input['conteo_sap'] ?? null) !== null) {
            $errors['conteo_sap'] = 'Solo una corrida completa, historico o complemento envía el conteo de SAP.';
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
     * A historical or complemento run whose rows do not match the SAP count
     * fails (422) and changes nothing: a historical range stays empty, ready
     * to be loaded again, and a complemento range keeps the weights and
     * shipping codes it had.
     *
     * @param  list<string>  $parts
     * @param  array<string, int>  $rows
     * @param  array<string, int>  $sapCounts
     */
    private function failMismatched(Run $run, array $parts, array $rows, array $sapCounts): never
    {
        $run->finish(RunState::Failed, 'El conteo de SAP no cuadra con las filas recibidas: '.implode(', ', $parts).'.');

        $outcome = $run->tipo === RunType::Complement
            ? 'la corrida complemento falló y no se cambió ninguna línea'
            : 'la carga histórica falló y el rango sigue vacío';

        throw RobotRequestRejected::invalid("El conteo de SAP no cuadra con las filas recibidas; {$outcome}.", array_combine(
            array_map(fn (string $part): string => "conteo_sap.{$part}", $parts),
            array_map(fn (string $part): string => "SAP contó {$sapCounts[$part]} filas y llegaron {$rows[$part]}.", $parts),
        ));
    }

    /**
     * A complemento run whose lines are not exactly the company's stored
     * lines of the range fails (422) and writes nothing. The answer gives
     * only how many lines are extra and how many are missing, never their
     * values.
     *
     * @param  array{sobran: int, faltan: int}  $unmatched
     */
    private function failUnmatched(Run $run, array $unmatched): never
    {
        ['sobran' => $extra, 'faltan' => $missing] = $unmatched;

        $run->finish(RunState::Failed, "Las líneas no cuadran con las de MySQL en el rango: sobran {$extra}, faltan {$missing}.");

        throw new RobotRequestRejected(422, 'Las líneas recibidas no cuadran con las de MySQL en el rango; la corrida complemento falló y no se cambió ninguna línea.', [
            'sobran' => $extra,
            'faltan' => $missing,
            'errors' => ['filas.ventas' => ["Sobran {$extra} líneas que no están en MySQL y faltan {$missing} del rango que no llegaron."]],
        ]);
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
