<?php

namespace App\Modules\Sap\Models;

use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Support\Carbon;

/**
 * A comparison of totals the robot reported (table robot_comparisons,
 * docs/contrato-robot.md, section 13.3).
 *
 * @property int $id
 * @property Dataset $conjunto
 * @property Company $empresa
 * @property Carbon|null $desde
 * @property Carbon|null $hasta
 * @property bool $cuadra
 * @property list<array{clave: string, campo: string, sap: string|null, mysql: string|null}> $diferencias
 * @property Carbon $comparada_en
 * @property string $robot_key
 * @property Carbon $created_at
 */
final class RobotComparison extends Model
{
    public const UPDATED_AT = null;

    protected $table = 'robot_comparisons';

    protected $fillable = ['conjunto', 'empresa', 'desde', 'hasta', 'cuadra', 'diferencias', 'comparada_en', 'robot_key'];

    protected function casts(): array
    {
        return [
            'conjunto' => Dataset::class,
            'empresa' => Company::class,
            'desde' => 'date',
            'hasta' => 'date',
            'cuadra' => 'boolean',
            'diferencias' => 'array',
            'comparada_en' => 'datetime',
        ];
    }
}
