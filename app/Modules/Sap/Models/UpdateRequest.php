<?php

namespace App\Modules\Sap\Models;

use App\Modules\Sap\Contracts\Data\UpdateRequestData;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\RequestScope;
use App\Modules\Sap\Contracts\Enums\RequestState;
use Carbon\CarbonImmutable;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Support\Carbon;

/**
 * An update request (table update_requests, docs/contrato-robot.md, section 7).
 *
 * @property int $id
 * @property Company $empresa
 * @property Dataset $conjunto
 * @property RequestScope|null $parte
 * @property RequestState $estado
 * @property Carbon|null $correr_desde
 * @property Carbon|null $tomada_en
 * @property Carbon|null $terminada_en
 * @property string|null $error
 * @property int|null $run_id
 * @property Carbon $created_at
 */
final class UpdateRequest extends Model
{
    protected $table = 'update_requests';

    protected $guarded = [];

    protected function casts(): array
    {
        return [
            'empresa' => Company::class,
            'conjunto' => Dataset::class,
            'parte' => RequestScope::class,
            'estado' => RequestState::class,
            'correr_desde' => 'datetime',
            'tomada_en' => 'datetime',
            'terminada_en' => 'datetime',
        ];
    }

    /**
     * Requests of the same company and dataset: they wait for each other.
     *
     * @param  Builder<self>  $query
     */
    public function scopeSisters(Builder $query, Company $company, Dataset $dataset): void
    {
        $query->where('empresa', $company)->where('conjunto', $dataset);
    }

    public function toData(bool $created = false): UpdateRequestData
    {
        return new UpdateRequestData(
            id: $this->id,
            company: $this->empresa,
            dataset: $this->conjunto,
            scope: $this->parte,
            state: $this->estado,
            runFrom: $this->correr_desde?->toImmutable(),
            takenAt: $this->tomada_en?->toImmutable(),
            finishedAt: $this->terminada_en?->toImmutable(),
            error: $this->error,
            requestedAt: CarbonImmutable::instance($this->created_at),
            created: $created,
        );
    }
}
