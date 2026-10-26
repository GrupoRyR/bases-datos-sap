<?php

namespace App\Modules\Sap\Domain\Runs;

/**
 * The life of a run (docs/contrato-robot.md, section 4.5): only an open run
 * takes batches, a close or a failure.
 */
enum RunState: string
{
    case Open = 'abierta';
    case Closed = 'cerrada';
    case Failed = 'fallida';
    case Expired = 'vencida';
}
