<?php

namespace App\Modules\Sap\Http\Controllers\Robot;

use App\Modules\Sap\Application\Runs\FailRun;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

/**
 * POST /api/robot/v1/corridas/{run}/fallar (docs/contrato-robot.md, section 4.4).
 */
final class FailRunController
{
    public function __invoke(Request $request, int $run, FailRun $fail): JsonResponse
    {
        $failed = $fail->handle($run, $request->input('error'));

        return response()->json(['run_id' => $failed->id, 'estado' => $failed->estado->value]);
    }
}
