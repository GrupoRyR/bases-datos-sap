<?php

namespace App\Modules\Sap\Contracts;

use App\Modules\Sap\Contracts\Data\RequestHistoryPage;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;

/**
 * The update requests with who asked for each one, newest first, for the
 * panel's history.
 */
interface RequestHistory
{
    /**
     * @param  int  $page  From 1; lower values read as 1.
     * @param  int  $perPage  Clamped to 1..100.
     */
    public function page(int $page = 1, int $perPage = 25, ?Company $company = null, ?Dataset $dataset = null): RequestHistoryPage;
}
