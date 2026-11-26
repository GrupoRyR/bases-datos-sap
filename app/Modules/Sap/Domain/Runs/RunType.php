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

    /** A manual VENTAS load of one month before the nightly window, into an empty range (section 10.4). */
    case Historical = 'historico';

    /** A manual VENTAS run of one month before the nightly window that fills only kilos and codigo_envio of the lines already stored (section 10.5). */
    case Complement = 'complemento';

    /**
     * Whether the run is a manual one of a VENTAS month before the nightly
     * window, with ventana_hasta (sections 10.4 and 10.5): it is never the
     * nightly count of a day nor the last update of the dataset.
     */
    public function isPastMonth(): bool
    {
        return in_array($this, [self::Historical, self::Complement], true);
    }

    /** Whether the run brings every part of the dataset in full and its SAP count. */
    public function isWhole(): bool
    {
        return $this !== self::Request;
    }
}
