<?php

namespace App\Modules\Sap\Contracts\Data;

use Carbon\CarbonImmutable;

/**
 * A run of the robot in short (docs/contrato-robot.md, section 4). type is
 * "completa" or "solicitud"; state is "abierta", "cerrada", "fallida" or
 * "vencida". startedAt is when the robot opened it.
 */
final readonly class RunSummaryData
{
    public function __construct(
        public int $id,
        public string $type,
        public string $state,
        public CarbonImmutable $startedAt,
        public ?CarbonImmutable $finishedAt,
        public ?string $error,
    ) {}
}
