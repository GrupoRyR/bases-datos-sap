<?php

namespace App\Modules\Sap\Contracts;

use App\Modules\Sap\Contracts\Data\ClientAppData;
use App\Modules\Sap\Contracts\Data\IssuedAppKey;

/**
 * The keys apps use to call /api/v1 (docs/contrato-robot.md, section 7.4).
 * Created, rotated and revoked from the panel; the key is shown once.
 */
interface ClientAppKeys
{
    public function issue(string $name): IssuedAppKey;

    /**
     * From now on the key gets 401. Its past requests stay recorded.
     */
    public function revoke(int $appId): void;

    /**
     * Every app, revoked ones included, ordered by name.
     *
     * @return list<ClientAppData>
     */
    public function all(): array;

    /**
     * Gives the app a new key; the old one gets 401 at once. A revoked app
     * works again with the new key.
     *
     * @throws \InvalidArgumentException when the app does not exist
     */
    public function rotate(int $appId): IssuedAppKey;
}
