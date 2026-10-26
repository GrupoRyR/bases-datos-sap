<?php

namespace App\Modules\Sap\Models;

use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Domain\Runs\RunState;
use App\Modules\Sap\Domain\Runs\RunType;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\LazyCollection;

/**
 * A run of the robot (table robot_runs, docs/contrato-robot.md, section 4).
 *
 * @property int $id
 * @property Dataset $conjunto
 * @property Company $empresa
 * @property RunType $tipo
 * @property array<string, string> $partes
 * @property list<int> $solicitudes
 * @property Carbon|null $fecha_corte
 * @property Carbon $extraida_en
 * @property RunState $estado
 * @property string|null $abierta_lock
 * @property Carbon $abierta_hasta
 * @property string $robot_key
 * @property int|null $batches
 * @property array<string, int>|null $filas
 * @property array<string, int>|null $conteo_sap
 * @property array<string, array<string, int|bool>>|null $conteo
 * @property int $lotes_rechazados
 * @property string|null $error
 * @property Carbon|null $aplicada_en
 * @property Carbon|null $terminada_en
 * @property Carbon $created_at
 */
final class Run extends Model
{
    /** A run with no batch for this long expires. */
    public const IDLE_MINUTES = 30;

    protected $table = 'robot_runs';

    protected $guarded = [];

    protected function casts(): array
    {
        return [
            'conjunto' => Dataset::class,
            'empresa' => Company::class,
            'tipo' => RunType::class,
            'estado' => RunState::class,
            'partes' => 'array',
            'solicitudes' => 'array',
            'filas' => 'array',
            'conteo_sap' => 'array',
            'conteo' => 'array',
            'fecha_corte' => 'date',
            'extraida_en' => 'datetime',
            'abierta_hasta' => 'datetime',
            'aplicada_en' => 'datetime',
            'terminada_en' => 'datetime',
        ];
    }

    /**
     * The value of abierta_lock while a run of this dataset and company is open.
     */
    public static function lockFor(Dataset $dataset, Company $company): string
    {
        return $dataset->value.':'.$company->value;
    }

    /**
     * Whether the run is open and still within its idle window.
     */
    public function isOpen(): bool
    {
        return $this->estado === RunState::Open && $this->abierta_hasta->isFuture();
    }

    /**
     * Ends the run as failed, expired or closed: frees its dataset and
     * company for the next run and discards its batches. The run row is
     * locked first, so a batch, a close or the scheduler racing for the same
     * run cannot both win. Returns false (and reloads the run) if it was no
     * longer open.
     */
    /**
     * @param  array<string, mixed>  $attributes  Saved with the new state, e.g. what a close applied.
     */
    public function finish(RunState $state, ?string $error = null, array $attributes = []): bool
    {
        return DB::transaction(function () use ($state, $error, $attributes): bool {
            $current = self::query()->whereKey($this->id)->lockForUpdate()->firstOrFail();

            if ($current->estado !== RunState::Open) {
                $this->setRawAttributes($current->getAttributes(), true);

                return false;
            }

            $this->forceFill([
                ...$attributes,
                'estado' => $state,
                'error' => $error,
                'abierta_lock' => null,
                'terminada_en' => now(),
            ])->save();

            DB::table('robot_batch_keys')->where('run_id', $this->id)->delete();
            DB::table('robot_batches')->where('run_id', $this->id)->delete();

            return true;
        });
    }

    /**
     * The rows the run received for a part, by column name, ten batches
     * (up to 10,000 rows) in memory at a time. Order does not matter: keys
     * never repeat within a run.
     *
     * @return LazyCollection<int, array<string, mixed>>
     */
    public function rowsOf(Part $part): LazyCollection
    {
        $columns = array_keys($part->columns());

        return DB::table('robot_batches')
            ->where('run_id', $this->id)
            ->where('parte', $part->value)
            ->lazyById(10, 'id')
            ->flatMap(fn (object $batch): array => array_map(
                fn (array $row): array => array_combine($columns, $row),
                json_decode((string) $batch->rows, true, flags: JSON_THROW_ON_ERROR),
            ));
    }

    /**
     * Expires the run if it is open but idle. Returns whether it did.
     */
    public function expireIfIdle(): bool
    {
        if ($this->estado !== RunState::Open || $this->abierta_hasta->isFuture()) {
            return false;
        }

        return $this->finish(RunState::Expired, 'Pasaron '.self::IDLE_MINUTES.' minutos sin recibir lotes.');
    }
}
