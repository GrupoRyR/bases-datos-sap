<?php

namespace App\Modules\Sap\Models;

use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Domain\Runs\RunState;
use App\Modules\Sap\Domain\Runs\RunType;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;

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
     * company for the next run and discards its batches.
     */
    public function finish(RunState $state, ?string $error = null): void
    {
        DB::transaction(function () use ($state, $error) {
            $this->forceFill([
                'estado' => $state,
                'error' => $error,
                'abierta_lock' => null,
                'terminada_en' => now(),
            ])->save();

            DB::table('robot_batch_keys')->where('run_id', $this->id)->delete();
            DB::table('robot_batches')->where('run_id', $this->id)->delete();
        });
    }

    /**
     * Expires the run if it is open but idle. Returns whether it did.
     */
    public function expireIfIdle(): bool
    {
        if ($this->estado !== RunState::Open || $this->abierta_hasta->isFuture()) {
            return false;
        }

        $this->finish(RunState::Expired, 'Pasaron '.self::IDLE_MINUTES.' minutos sin recibir lotes.');

        return true;
    }
}
