<?php

namespace App\Modules\Sap\Domain\Runs;

/**
 * How a part comes in a run (docs/contrato-robot.md, section 4.1).
 */
enum PartMode: string
{
    /** Every row SAP has: on close, rows of the part that did not come become inactive. */
    case Full = 'todo';

    /** Only rows that changed: nothing becomes inactive for being absent. */
    case Changes = 'cambios';
}
