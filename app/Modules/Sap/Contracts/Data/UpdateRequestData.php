<?php

namespace App\Modules\Sap\Contracts\Data;

use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\RequestScope;
use App\Modules\Sap\Contracts\Enums\RequestState;
use Carbon\CarbonImmutable;

/**
 * An update request as other modules see it. runFrom is when it runs (null
 * while it waits for a sister the robot is serving); created is false when
 * the call joined an existing identical request.
 */
final readonly class UpdateRequestData
{
    public function __construct(
        public int $id,
        public Company $company,
        public Dataset $dataset,
        public ?RequestScope $scope,
        public RequestState $state,
        public ?CarbonImmutable $runFrom,
        public ?CarbonImmutable $takenAt,
        public ?CarbonImmutable $finishedAt,
        public ?string $error,
        public CarbonImmutable $requestedAt,
        public bool $created = false,
    ) {}
}
