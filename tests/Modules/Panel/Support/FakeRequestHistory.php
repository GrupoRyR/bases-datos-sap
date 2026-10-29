<?php

namespace Tests\Modules\Panel\Support;

use App\Modules\Sap\Contracts\Data\RequesterData;
use App\Modules\Sap\Contracts\Data\RequestHistoryItem;
use App\Modules\Sap\Contracts\Data\RequestHistoryPage;
use App\Modules\Sap\Contracts\Data\UpdateRequestData;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\RequestScope;
use App\Modules\Sap\Contracts\Enums\RequestState;
use App\Modules\Sap\Contracts\RequestHistory;
use Carbon\CarbonImmutable;

/**
 * RequestHistory that returns the items it was given as one page and
 * records the arguments of every call, so panel tests never touch the Sap
 * tables. $total defaults to the number of items.
 */
final class FakeRequestHistory implements RequestHistory
{
    /** @var list<array{page: int, perPage: int, company: ?Company, dataset: ?Dataset}> */
    public array $calls = [];

    /**
     * @param  list<RequestHistoryItem>  $items
     */
    public function __construct(
        private array $items = [],
        private ?int $total = null,
    ) {}

    public function page(int $page = 1, int $perPage = 25, ?Company $company = null, ?Dataset $dataset = null): RequestHistoryPage
    {
        $this->calls[] = compact('page', 'perPage', 'company', 'dataset');

        return new RequestHistoryPage($this->items, $this->total ?? count($this->items), max(1, $page), $perPage);
    }

    /**
     * A request of SGX MAESTROS asked from the panel at 10:40 Bogota, with
     * sensible defaults unless the caller overrides them.
     *
     * @param  list<RequesterData>|null  $requesters
     */
    public static function item(
        int $id = 118,
        Company $company = Company::Sgx,
        Dataset $dataset = Dataset::Maestros,
        ?RequestScope $scope = null,
        RequestState $state = RequestState::Done,
        ?string $runFrom = null,
        ?string $finishedAt = '2026-10-29 10:44',
        ?string $error = null,
        string $requestedAt = '2026-10-29 10:40',
        ?array $requesters = null,
    ): RequestHistoryItem {
        $at = fn (?string $moment): ?CarbonImmutable => $moment === null ? null : CarbonImmutable::parse($moment, 'America/Bogota');

        return new RequestHistoryItem(
            new UpdateRequestData(
                id: $id,
                company: $company,
                dataset: $dataset,
                scope: $scope,
                state: $state,
                runFrom: $at($runFrom),
                takenAt: null,
                finishedAt: $at($finishedAt),
                error: $error,
                requestedAt: CarbonImmutable::parse($requestedAt, 'America/Bogota'),
            ),
            $requesters ?? [self::requester()],
        );
    }

    public static function requester(
        ?string $app = null,
        string $email = 'ana@segurex.com',
        ?string $name = 'Ana Ruiz',
        string $joinedAt = '2026-10-29 10:40',
    ): RequesterData {
        return new RequesterData($app, $email, $name, CarbonImmutable::parse($joinedAt, 'America/Bogota'));
    }
}
