<?php

namespace App\Modules\Sap\Http\Controllers\Robot;

use App\Modules\Sap\Application\Requests\TakeRequests;
use App\Modules\Sap\Http\Exceptions\RobotRequestRejected;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

/**
 * POST /api/robot/v1/solicitudes/tomar (docs/contrato-robot.md, section 7.3).
 * The robot asks every minute, without the VPN; an empty list means there
 * is nothing to do.
 */
final class TakeRequestsController
{
    public function __invoke(Request $request, TakeRequests $requests): JsonResponse
    {
        $max = $request->input('max', 20);

        if (! is_int($max) || $max < 1 || $max > 100) {
            throw RobotRequestRejected::invalid('La consulta no cumple el contrato.', ['max' => 'Debe ser un entero entre 1 y 100.']);
        }

        return response()->json(['solicitudes' => $requests->take($max)]);
    }
}
