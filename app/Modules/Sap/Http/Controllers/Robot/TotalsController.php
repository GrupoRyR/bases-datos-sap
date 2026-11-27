<?php

namespace App\Modules\Sap\Http\Controllers\Robot;

use App\Modules\Sap\Application\Totals\ComputeTotals;
use App\Modules\Sap\Application\Totals\TotalsScope;
use App\Modules\Sap\Http\Exceptions\RobotRequestRejected;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

/**
 * POST /api/robot/v1/totales (docs/contrato-robot.md, section 13.2). Read
 * only: the totals of MySQL the robot compares with SAP.
 */
final class TotalsController
{
    public function __invoke(Request $request, ComputeTotals $totals): JsonResponse
    {
        $errors = [];
        $scope = TotalsScope::fromInput($request->all(), $errors);

        if ($scope === null) {
            throw RobotRequestRejected::invalid('La consulta no cumple el contrato.', $errors);
        }

        return response()->json($totals->handle($scope));
    }
}
