<?php

namespace App\Modules\Sap\Domain\Runs;

/**
 * Why a run happens (docs/contrato-robot.md, section 4.1).
 */
enum RunType: string
{
    /** The nightly run at 02:00: every part of the dataset, all in full. */
    case Full = 'completa';

    /** A run that serves update requests. */
    case Request = 'solicitud';
}
