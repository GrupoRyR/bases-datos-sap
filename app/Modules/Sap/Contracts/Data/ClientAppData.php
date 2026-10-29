<?php

namespace App\Modules\Sap\Contracts\Data;

use Carbon\CarbonImmutable;

/**
 * An app with an API key, as the panel lists it. keyPrefix is the start of
 * its key, to recognize it; the key itself is never shown again.
 */
final readonly class ClientAppData
{
    public function __construct(
        public int $id,
        public string $name,
        public string $keyPrefix,
        public CarbonImmutable $createdAt,
        public ?CarbonImmutable $lastUsedAt,
        public ?CarbonImmutable $revokedAt,
    ) {}
}
