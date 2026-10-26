<?php

namespace App\Modules\Sap\Application\Runs;

use App\Modules\Sap\Domain\Runs\RunState;
use App\Modules\Sap\Http\Exceptions\RobotRequestRejected;
use App\Modules\Sap\Models\Run;

/**
 * Marks an open run as failed with the robot's message and discards its
 * batches (docs/contrato-robot.md, section 4.4). Data already in MySQL
 * stays as it was.
 */
final class FailRun
{
    public function __construct(private readonly OpenRuns $runs) {}

    public function handle(int $runId, mixed $error): Run
    {
        $run = $this->runs->find($runId);
        $error = is_string($error) ? trim($error) : '';

        if ($error === '' || mb_strlen($error) > 1000) {
            throw RobotRequestRejected::invalid('La falla no cumple el contrato.', [
                'error' => 'Debe traer el error, de hasta 1.000 caracteres.',
            ]);
        }

        if (! $run->finish(RunState::Failed, $error)) {
            throw new RobotRequestRejected(409, 'La corrida ya no está abierta.', ['estado' => $run->estado->value]);
        }

        return $run;
    }
}
