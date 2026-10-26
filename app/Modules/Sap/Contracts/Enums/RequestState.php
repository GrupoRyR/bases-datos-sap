<?php

namespace App\Modules\Sap\Contracts\Enums;

/**
 * The states of an update request (docs/contrato-robot.md, section 7.2).
 */
enum RequestState: string
{
    /** Ready for the robot to take. */
    case Pending = 'pendiente';

    /** Waits for its time: the 3 minutes, a blocked slot or a sister being served. */
    case Queued = 'en_cola';

    /** The robot took it and is working on it. */
    case Taken = 'tomada';

    /** Its run closed well. */
    case Done = 'terminada';

    /** Its run failed. */
    case Failed = 'fallida';

    /** Taken for more than 30 minutes without finishing. */
    case Expired = 'vencida';

    /**
     * Whether a new identical request joins this one instead of creating another.
     */
    public function isWaiting(): bool
    {
        return in_array($this, [self::Pending, self::Queued], true);
    }
}
