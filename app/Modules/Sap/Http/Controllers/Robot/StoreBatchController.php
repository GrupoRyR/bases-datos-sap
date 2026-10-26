<?php

namespace App\Modules\Sap\Http\Controllers\Robot;

use App\Modules\Sap\Application\Runs\ReceiveBatch;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

/**
 * POST /api/robot/v1/corridas/{run}/lotes (docs/contrato-robot.md, section 4.2).
 * 201 for a new batch, 200 with "duplicate" for the same batch sent again.
 */
final class StoreBatchController
{
    public function __invoke(Request $request, int $run, ReceiveBatch $receive): JsonResponse
    {
        $result = $receive->handle($run, $request->all(), (string) $request->attributes->get('robot_body'));

        return response()->json($result, isset($result['duplicate']) ? 200 : 201);
    }
}
