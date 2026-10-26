<?php

namespace App\Modules\Sap\Application\Runs;

use App\Modules\Sap\Http\Exceptions\RobotRequestRejected;
use App\Modules\Sap\Models\Run;

/**
 * Finds the run a robot request is about and makes sure it is still open
 * (docs/contrato-robot.md, section 4.5): 404 if it does not exist, 409 with
 * its state if it is no longer open. An idle run expires on the spot.
 */
final class OpenRuns
{
    public function find(int $runId): Run
    {
        $run = Run::find($runId) ?? throw new RobotRequestRejected(404, 'La corrida no existe.');

        $run->expireIfIdle();

        if (! $run->isOpen()) {
            throw new RobotRequestRejected(409, 'La corrida ya no está abierta.', ['estado' => $run->estado->value]);
        }

        return $run;
    }

    /**
     * Expires every open run past its idle window. Returns how many.
     */
    public function expireIdle(): int
    {
        return Run::where('estado', 'abierta')
            ->where('abierta_hasta', '<=', now())
            ->get()
            ->filter(fn (Run $run): bool => $run->expireIfIdle())
            ->count();
    }
}
