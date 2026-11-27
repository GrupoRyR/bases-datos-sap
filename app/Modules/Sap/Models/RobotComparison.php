<?php

namespace App\Modules\Sap\Models;

use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use Illuminate\Database\Eloquent\Casts\Attribute;
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
            'comparada_en' => 'datetime',
        ];
    }

    /**
     * The differences as JSON, read back with their keys in contract order:
     * MySQL's JSON type keeps object keys sorted its own way.
     *
     * @return Attribute<list<array{clave: string, campo: string, sap: string|null, mysql: string|null}>, list<array{clave: string, campo: string, sap: string|null, mysql: string|null}>>
     */
    protected function diferencias(): Attribute
    {
        return Attribute::make(
            get: fn (?string $value): array => array_map(
                fn (array $difference): array => [
                    'clave' => $difference['clave'],
                    'campo' => $difference['campo'],
                    'sap' => $difference['sap'],
                    'mysql' => $difference['mysql'],
                ],
                (array) json_decode($value ?? '[]', true, flags: JSON_THROW_ON_ERROR),
            ),
            set: fn (array $value): string => json_encode($value, JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE),
        );
    }
}
