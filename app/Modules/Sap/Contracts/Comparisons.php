<?php

namespace App\Modules\Sap\Contracts;

use App\Modules\Sap\Contracts\Data\ComparisonData;

/**
 * The robot's comparisons of its totals of SAP with those of MySQL
 * (docs/contrato-robot.md, section 13.3), for the panel.
 */
interface Comparisons
{
    /**
     * The latest comparison of each company and dataset that has one (by
     * comparada_en, then the newest received), in company order, then
     * dataset order.
     *
     * @return list<ComparisonData>
     */
    public function latest(): array;
}
