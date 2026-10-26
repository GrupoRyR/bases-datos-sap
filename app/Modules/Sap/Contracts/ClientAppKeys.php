<?php

namespace App\Modules\Sap\Contracts;

use App\Modules\Sap\Contracts\Data\IssuedAppKey;

/**
 * The keys apps use to call /api/v1 (docs/contrato-robot.md, section 7.4).
 * Created and revoked from the panel; the key is shown once.
 */
interface ClientAppKeys
{
    public function issue(string $name): IssuedAppKey;

    /**
     * From now on the key gets 401. Its past requests stay recorded.
     */
    public function revoke(int $appId): void;
}
