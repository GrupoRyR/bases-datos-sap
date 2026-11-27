<?php

namespace App\Modules\Sap\Http\Controllers\Robot;

use App\Modules\Sap\Application\Totals\StoreComparison;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

/**
 * POST /api/robot/v1/comparaciones (docs/contrato-robot.md, section 13.3).
 * Stores the robot's comparison with SAP; never applies it to the data.
 */
final class StoreComparisonController
{
    public function __invoke(Request $request, StoreComparison $store): JsonResponse
    {
        $comparison = $store->handle($request->all(), (string) $request->attributes->get('robot_key'));

        return response()->json(['id' => $comparison->id], 201);
    }
}
