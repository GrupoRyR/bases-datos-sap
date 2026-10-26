<?php

namespace App\Modules\Sap\Application\Apps;

use App\Modules\Sap\Contracts\ClientAppKeys;
use App\Modules\Sap\Contracts\Data\IssuedAppKey;
use App\Modules\Sap\Models\ClientApp;
use Illuminate\Support\Str;

/**
 * Issues, finds and revokes app keys. Keys are "bsap_" plus 48 random
 * characters; only their SHA-256 and first characters are stored.
 */
final class AppKeys implements ClientAppKeys
{
    public function issue(string $name): IssuedAppKey
    {
        $key = 'bsap_'.Str::random(48);

        $app = ClientApp::create([
            'nombre' => trim($name),
            'key_hash' => hash('sha256', $key),
            'key_prefix' => substr($key, 0, 12),
        ]);

        return new IssuedAppKey($app->id, $app->nombre, $key);
    }

    public function revoke(int $appId): void
    {
        ClientApp::whereKey($appId)->whereNull('revoked_at')->update(['revoked_at' => now()]);
    }

    /**
     * The app of a key that is not revoked. Looked up by hash, so the
     * comparison never depends on the key's characters.
     */
    public function find(string $key): ?ClientApp
    {
        return ClientApp::where('key_hash', hash('sha256', $key))->whereNull('revoked_at')->first();
    }
}
