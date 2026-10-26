<?php

namespace App\Modules\Sap\Domain\Runs;

use App\Modules\Sap\Models\Run;

/**
 * A run closed, failed or expired. Dispatched inside the transaction that
 * ends it, so whatever reacts (its update requests) commits with it.
 */
final readonly class RunFinished
{
    public function __construct(public Run $run) {}
}
