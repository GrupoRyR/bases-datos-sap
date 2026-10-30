<?php

namespace App\Modules\Sap\Contracts\Data;

use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Part;
use Carbon\CarbonImmutable;

/**
 * A customer, supplier or item found by MasterLookup, with only its
 * identifying fields. taxId is the NIT (always null for items).
 */
final readonly class MasterRecordData
{
    public function __construct(
        public Company $company,
        public Part $part,
        public string $code,
        public string $name,
        public ?string $taxId,
        public bool $active,
        public ?CarbonImmutable $updatedInSap,
        public CarbonImmutable $syncedAt,
    ) {}
}
