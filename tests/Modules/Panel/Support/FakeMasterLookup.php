<?php

namespace Tests\Modules\Panel\Support;

use App\Modules\Sap\Contracts\Data\MasterRecordData;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Contracts\MasterLookup;
use Carbon\CarbonImmutable;

/**
 * MasterLookup that returns the records it was given and records the
 * arguments of every call, so panel tests never touch the Sap views.
 */
final class FakeMasterLookup implements MasterLookup
{
    /** @var list<array{part: Part, term: string, company: ?Company, limit: int}> */
    public array $calls = [];

    /**
     * @param  list<MasterRecordData>  $records
     */
    public function __construct(private array $records = []) {}

    public function search(Part $part, string $term, ?Company $company = null, int $limit = 10): array
    {
        $this->calls[] = compact('part', 'term', 'company', 'limit');

        return $this->records;
    }

    /**
     * A record with sensible defaults; times are read in Bogota.
     */
    public static function record(
        Company $company = Company::Sgx,
        Part $part = Part::Customers,
        string $code = 'C800123456',
        string $name = 'Ferretería Andina SAS',
        ?string $taxId = '800123456-1',
        bool $active = true,
        ?string $updatedInSap = '2026-10-23 09:15',
        string $syncedAt = '2026-10-29 02:15',
    ): MasterRecordData {
        return new MasterRecordData(
            company: $company,
            part: $part,
            code: $code,
            name: $name,
            taxId: $taxId,
            active: $active,
            updatedInSap: $updatedInSap === null ? null : CarbonImmutable::parse($updatedInSap, 'America/Bogota'),
            syncedAt: CarbonImmutable::parse($syncedAt, 'America/Bogota'),
        );
    }
}
