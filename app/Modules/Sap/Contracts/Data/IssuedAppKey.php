<?php

namespace App\Modules\Sap\Contracts\Data;

/**
 * A new app key. The key itself is shown only here, once: the database keeps
 * its SHA-256 and its first 12 characters, the prefix the panel and the audit
 * log name it by (docs/plan-bases-sap.md, section 8).
 */
final readonly class IssuedAppKey
{
    public function __construct(
        public int $id,
        public string $name,
        public string $key,
        public string $keyPrefix,
    ) {}
}
