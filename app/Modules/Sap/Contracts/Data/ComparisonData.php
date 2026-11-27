<?php

namespace App\Modules\Sap\Contracts\Data;

use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use Carbon\CarbonImmutable;

/**
 * A comparison the robot reported (docs/contrato-robot.md, section 13.3).
 * from and until are the VENTAS posting dates compared ("YYYY-MM-DD", both
 * included), null when the whole dataset was; matches is "cuadra";
 * differences is empty when it matches. comparedAt is when the robot
 * compared and receivedAt when the API stored it, both in Bogota.
 */
final readonly class ComparisonData
{
    /**
     * @param  list<array{clave: string, campo: string, sap: string|null, mysql: string|null}>  $differences
     */
    public function __construct(
        public int $id,
        public Company $company,
        public Dataset $dataset,
        public ?string $from,
        public ?string $until,
        public bool $matches,
        public array $differences,
        public CarbonImmutable $comparedAt,
        public CarbonImmutable $receivedAt,
    ) {}
}
