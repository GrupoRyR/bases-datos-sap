<?php

namespace App\Modules\Sap\Contracts\Data;

use Carbon\CarbonImmutable;

/**
 * Someone who created or joined an update request. app is the name of the
 * client app that asked; null when it came from the panel.
 */
final readonly class RequesterData
{
    public function __construct(
        public ?string $app,
        public string $email,
        public ?string $name,
        public CarbonImmutable $joinedAt,
    ) {}
}
