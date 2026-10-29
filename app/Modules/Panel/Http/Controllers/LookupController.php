<?php

namespace App\Modules\Panel\Http\Controllers;

use App\Modules\Panel\Http\Requests\LookupRequest;
use App\Modules\Panel\Support\LookupPage;
use App\Modules\Sap\Contracts\MasterLookup;
use Illuminate\Http\Response;

/**
 * GET and POST /panel/consulta (panel.consulta, panel.consulta.buscar):
 * finds customers, suppliers and items through MasterLookup so TI can check
 * what arrived from SAP. The term can be a NIT or a name (Ley 1581): it only
 * travels in the POST body, the results are rendered from that POST with no
 * redirect, nothing goes to the session, and the term is never audited or
 * logged. The GET ignores its query string, so no search runs from a URL.
 */
final class LookupController
{
    public function create(): Response
    {
        return LookupPage::response(['parte' => '', 'empresa' => '', 'termino' => '']);
    }

    public function search(LookupRequest $request, MasterLookup $lookup): Response
    {
        $records = $lookup->search($request->part(), $request->term(), $request->company(), MasterLookup::MAX_RESULTS);

        return LookupPage::response($request->values(), $records);
    }
}
