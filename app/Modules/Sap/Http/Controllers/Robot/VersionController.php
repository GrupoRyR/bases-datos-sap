<?php

namespace App\Modules\Sap\Http\Controllers\Robot;

use App\Modules\Sap\Application\Deploy\DeployedCommit;
use Illuminate\Http\JsonResponse;

/**
 * POST /api/robot/v1/version (docs/contrato-robot.md, section 13.1). The
 * robot only updates itself to the commit the server already runs.
 */
final class VersionController
{
    public function __invoke(DeployedCommit $commit): JsonResponse
    {
        return response()->json(['commit' => $commit->current()]);
    }
}
