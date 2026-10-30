<?php

namespace Tests\Modules\Panel\Support;

use App\Modules\Sap\Contracts\Data\UpdateRequestData;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\RequestScope;
use App\Modules\Sap\Contracts\Enums\RequestState;
use App\Modules\Sap\Contracts\UpdateRequests;
use Carbon\CarbonImmutable;

/**
 * UpdateRequests that records every call and answers with request 118 in
 * the configured state, so panel tests never touch the Sap tables.
 */
final class FakeUpdateRequests implements UpdateRequests
{
    /** @var list<array{company: Company, dataset: Dataset, scope: ?RequestScope, email: string, name: ?string}> */
    public array $calls = [];

    public function __construct(
        private RequestState $state = RequestState::Pending,
        private ?string $runFrom = '2026-10-29 10:40',
        private bool $created = true,
    ) {}

    public function request(Company $company, Dataset $dataset, ?RequestScope $scope, string $email, ?string $name): UpdateRequestData
    {
        $this->calls[] = compact('company', 'dataset', 'scope', 'email', 'name');

        return new UpdateRequestData(
            id: 118,
            company: $company,
            dataset: $dataset,
            scope: $scope,
            state: $this->state,
            runFrom: $this->runFrom === null ? null : CarbonImmutable::parse($this->runFrom, 'America/Bogota'),
            takenAt: null,
            finishedAt: null,
            error: null,
            requestedAt: CarbonImmutable::parse('2026-10-29 10:40', 'America/Bogota'),
            created: $this->created,
        );
    }
}
