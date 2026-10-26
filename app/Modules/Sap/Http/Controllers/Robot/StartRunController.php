<?php

namespace App\Modules\Sap\Http\Controllers\Robot;

use App\Modules\Sap\Application\Runs\StartRun;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

/**
 * POST /api/robot/v1/corridas (docs/contrato-robot.md, section 4.1).
 */
final class StartRunController
{
    public function __invoke(Request $request, StartRun $start): JsonResponse
    {
        $run = $start->handle($request->all(), (string) $request->attributes->get('robot_key'));

        return response()->json([
            'run_id' => $run->id,
            'estado' => $run->estado->value,
            'abierta_hasta' => $run->abierta_hasta->toIso8601String(),
        ], 201);
    }
}
