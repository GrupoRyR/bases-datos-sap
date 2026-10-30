<?php

namespace App\Modules\Sap\Contracts;

use App\Modules\Sap\Contracts\Data\MasterRecordData;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Part;

/**
 * Finds customers, suppliers and items in their stable views so TI can
 * check what arrived. It returns only identifying fields (Ley 1581): never
 * phones, e-mails or addresses.
 */
interface MasterLookup
{
    /** No search returns more rows than this. */
    public const MAX_RESULTS = 25;

    /**
     * Rows whose code starts with the term, whose name contains it or whose
     * tax id starts with it, ignoring case; ordered by name, company and code.
     *
     * @param  int  $limit  Clamped to 1..MAX_RESULTS.
     * @return list<MasterRecordData>
     *
     * @throws \InvalidArgumentException when the part is not customers, suppliers or
     *                                   items, or the trimmed term has fewer than 2 characters
     */
    public function search(Part $part, string $term, ?Company $company = null, int $limit = 10): array;
}
