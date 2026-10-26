<?php

namespace App\Modules\Sap\Contracts\Enums;

/**
 * The SAP Business One companies (docs/plan-bases-sap.md, section 1). Both
 * live on the same HANA server, each in its own schema.
 */
enum Company: string
{
    /** Segurex LATAM SAS, schema SEGUREX. */
    case Sgx = 'SGX';

    /** Soluciones y Derivados de Colombia SAS, schema HBT_SDERIVADOS. */
    case Sdc = 'SDC';
}
