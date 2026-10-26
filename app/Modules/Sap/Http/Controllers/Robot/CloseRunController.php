<?php

namespace App\Modules\Sap\Http\Controllers\Robot;

use App\Modules\Sap\Application\Runs\CloseRun;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

/**
 * POST /api/robot/v1/corridas/{run}/cerrar (docs/contrato-robot.md, section 4.3).
 */
final class CloseRunController
{
    public function __invoke(Request $request, int $run, CloseRun $close): JsonResponse
    {
        $closed = $close->handle($run, $request->all());

        return response()->json([
            'run_id' => $closed->id,
            'estado' => $closed->estado->value,
            'aplicada_en' => $closed->aplicada_en?->toIso8601String(),
        ]);
    }
}
