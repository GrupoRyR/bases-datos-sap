<?php

namespace App\Modules\Sap\Application\Runs;

use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Domain\Batches\BatchRows;
use App\Modules\Sap\Domain\Runs\RunState;
use App\Modules\Sap\Http\Exceptions\RobotRequestRejected;
use App\Modules\Sap\Models\Run;
use Illuminate\Support\Facades\DB;

/**
 * Stores one batch of an open run until the run closes
 * (docs/contrato-robot.md, section 4.2). Nothing reaches the dataset
 * tables here, so a refused batch leaves every table as it was.
 */
final class ReceiveBatch
{
    /** Rows per batch, at most. */
    public const MAX_ROWS = 1000;

    public function __construct(private readonly OpenRuns $runs) {}

    /**
     * @param  array<string, mixed>  $input
     * @param  string  $body  The inflated JSON body, compared by SHA-256 on a resend.
     * @return array{batch: int, rows: int, duplicate?: true}
     */
    public function handle(int $runId, array $input, string $body): array
    {
        $run = $this->runs->find($runId);
        $number = $input['batch'] ?? null;
        $sha256 = hash('sha256', $body);

        if (! is_int($number) || $number < 1) {
            $this->refuse($run, ['batch' => 'Debe ser un entero desde 1.']);
        }

        $duplicate = $this->resent($run, $number, $sha256);

        if ($duplicate !== null) {
            return $duplicate;
        }

        $part = Part::tryFrom(is_string($input['parte'] ?? null) ? $input['parte'] : '');

        if ($part === null || ! array_key_exists($part->value, $run->partes)) {
            $this->refuse($run, ['parte' => 'La parte no está en la corrida.']);
        }

        $rows = $input['rows'] ?? null;

        if (! is_array($rows) || ! array_is_list($rows) || $rows === [] || count($rows) > self::MAX_ROWS) {
            $this->refuse($run, ['rows' => 'Un lote trae entre 1 y 1.000 filas.']);
        }

        $checked = BatchRows::check($part, $input['columns'] ?? null, $rows);

        if ($checked['errors'] !== []) {
            $this->refuse($run, $checked['errors']);
        }

        $outside = $this->outsideWindow($run, $part, $checked['rows']);

        if ($outside !== []) {
            $this->refuse($run, $outside);
        }

        try {
            return $this->store($run, $number, $part, $checked['rows'], $sha256);
        } catch (RobotRequestRejected $rejected) {
            // A repeated key is only found against the stored ones.
            if ($rejected->status === 422) {
                Run::query()->whereKey($run->id)->increment('lotes_rechazados');
            }

            throw $rejected;
        }
    }

    /**
     * A VENTAS line posted before the run's window would reach a month the
     * close never touches (contract section 10.1): the batch is refused.
     *
     * @param  list<list<mixed>>  $rows
     * @return array<string, string>
     */
    private function outsideWindow(Run $run, Part $part, array $rows): array
    {
        // StartRun always stores the window of a VENTAS run.
        $from = $run->ventana_desde?->toDateString();

        if ($part !== Part::Sales || $from === null) {
            return [];
        }

        $position = array_search('fecha_contabilizacion', array_keys($part->columns()), true);
        $errors = [];

        foreach ($rows as $index => $row) {
            if ($row[$position] < $from) {
                $errors["rows.{$index}.fecha_contabilizacion"] = "Es anterior a ventana_desde ({$from}).";
            }
        }

        return array_slice($errors, 0, BatchRows::MAX_ERRORS, true);
    }

    /**
     * The answer to a batch number the run already has: 200 with duplicate
     * for the same body, 409 for another one; null for a new number.
     *
     * @return array{batch: int, rows: int, duplicate: true}|null
     */
    private function resent(Run $run, int $number, string $sha256): ?array
    {
        $previous = DB::table('robot_batches')->where('run_id', $run->id)->where('batch', $number)->first();

        if ($previous === null) {
            return null;
        }

        if ($previous->sha256 !== $sha256) {
            throw new RobotRequestRejected(409, 'Ese lote ya llegó con otro contenido.', ['estado' => $run->estado->value]);
        }

        return ['batch' => $number, 'rows' => (int) $previous->rows_count, 'duplicate' => true];
    }

    /**
     * Saves the batch and its keys under a lock on the run, so batches of
     * the same run and its close or expiry never interleave. A copy of the
     * same batch stored meanwhile (a resend racing the original) is a
     * duplicate, not a conflict.
     *
     * @param  list<list<mixed>>  $rows
     * @return array{batch: int, rows: int, duplicate?: true}
     */
    private function store(Run $run, int $number, Part $part, array $rows, string $sha256): array
    {
        return DB::transaction(function () use ($run, $number, $part, $rows, $sha256): array {
            $current = Run::query()->whereKey($run->id)->lockForUpdate()->firstOrFail();

            if ($current->estado !== RunState::Open) {
                throw new RobotRequestRejected(409, 'La corrida ya no está abierta.', ['estado' => $current->estado->value]);
            }

            $duplicate = $this->resent($current, $number, $sha256);

            if ($duplicate !== null) {
                return $duplicate;
            }

            if ($part->key() !== []) {
                $this->storeKeys($run, $part, $rows);
            }

            DB::table('robot_batches')->insert([
                'run_id' => $run->id,
                'batch' => $number,
                'parte' => $part->value,
                'sha256' => $sha256,
                'rows_count' => count($rows),
                'rows' => json_encode($rows, JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR),
                'created_at' => now(),
            ]);

            $current->forceFill(['abierta_hasta' => now()->addMinutes(Run::IDLE_MINUTES)])->save();

            return ['batch' => $number, 'rows' => count($rows)];
        });
    }

    /**
     * Refuses a key already seen in this batch or in an earlier one.
     *
     * @param  list<list<mixed>>  $rows
     */
    private function storeKeys(Run $run, Part $part, array $rows): void
    {
        $hashes = array_map(fn (array $row): string => BatchRows::keyHash($part, $row), $rows);
        $seen = [];

        foreach (array_chunk(array_unique($hashes), 500) as $chunk) {
            $seen += array_flip(DB::table('robot_batch_keys')
                ->where('run_id', $run->id)->where('parte', $part->value)->whereIn('key_hash', $chunk)
                ->pluck('key_hash')->all());
        }

        $errors = [];
        $field = "rows.%d.{$part->key()[0]}";

        foreach ($hashes as $index => $hash) {
            if (isset($seen[$hash])) {
                $errors[sprintf($field, $index)] = 'La llave se repite en la corrida.';
            }

            $seen[$hash] = true;
        }

        if ($errors !== []) {
            throw RobotRequestRejected::invalid('El lote repite llaves de la corrida.', $errors);
        }

        foreach (array_chunk(array_unique($hashes), 500) as $chunk) {
            DB::table('robot_batch_keys')->insert(array_map(
                fn (string $hash): array => ['run_id' => $run->id, 'parte' => $part->value, 'key_hash' => $hash],
                $chunk,
            ));
        }
    }

    /**
     * Counts the refused batch on the run and answers 422; the run stays open.
     *
     * @param  array<string, string>  $errors
     */
    private function refuse(Run $run, array $errors): never
    {
        Run::query()->whereKey($run->id)->increment('lotes_rechazados');

        throw RobotRequestRejected::invalid('El lote no cumple el contrato.', $errors);
    }
}
