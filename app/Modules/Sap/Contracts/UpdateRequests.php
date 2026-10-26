<?php

namespace App\Modules\Sap\Contracts;

use App\Modules\Sap\Contracts\Data\UpdateRequestData;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\RequestScope;

/**
 * Asks for an update of SAP data with the rules of docs/contrato-robot.md,
 * section 7.2: it joins an identical waiting request, waits behind a sister
 * being served or finished less than 3 minutes ago, and steps out of the
 * blocked slots. It is never refused. The panel's button uses it.
 */
interface UpdateRequests
{
    /**
     * @param  RequestScope|null  $scope  Only for MAESTROS; null asks for the whole dataset.
     *
     * @throws \InvalidArgumentException when the scope does not belong to the dataset
     */
    public function request(Company $company, Dataset $dataset, ?RequestScope $scope, string $email, ?string $name): UpdateRequestData;
}
