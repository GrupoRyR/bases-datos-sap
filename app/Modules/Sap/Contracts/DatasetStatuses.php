<?php

namespace App\Modules\Sap\Contracts;

use App\Modules\Sap\Contracts\Data\DatasetStatusData;

/**
 * How each dataset of each company stands: when it was last applied, its
 * rows in MySQL and its latest run. The panel's home shows it.
 */
interface DatasetStatuses
{
    /**
     * One status per company and dataset, in company order, then dataset order.
     *
     * @return list<DatasetStatusData>
     */
    public function all(): array;
}
