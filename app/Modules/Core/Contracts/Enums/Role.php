<?php

namespace App\Modules\Core\Contracts\Enums;

/**
 * The roles of the TI panel (users.role). A user without a role signs in
 * but sees nothing until TI gives them one (php artisan core:rol).
 *
 * Other modules check access through the gates core.consultar and
 * core.administrar (Core README) rather than comparing roles.
 */
enum Role: string
{
    /** Manages everything: requests, connected apps and users. */
    case AdminTi = 'admin_ti';

    /** Reads the panel: runs, counts and the audit log. */
    case Consulta = 'consulta';

    public function label(): string
    {
        return match ($this) {
            self::AdminTi => 'Admin TI',
            self::Consulta => 'Consulta',
        };
    }
}
