<?php

namespace App\Modules\Sap\Contracts;

use App\Modules\Sap\Contracts\Data\StabilityData;

/**
 * The stability counter of docs/plan-bases-sap.md, section 6 («Estable: 9
 * de 14 días»). A Bogota day is stable when every nightly run closed well,
 * every nightly count matched and every update request finished in less
 * than 10 minutes. Criterion 4 (nobody fixed data by hand) cannot be
 * measured from the data, so the counter leaves it out.
 */
interface Stability
{
    /** Stable days in a row the plan asks for. */
    public const TARGET_DAYS = 14;

    public function current(): StabilityData;
}
