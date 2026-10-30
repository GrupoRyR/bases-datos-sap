<?php

namespace App\Modules\Sap\Application\Apps;

use App\Modules\Sap\Contracts\ClientAppKeys;
use App\Modules\Sap\Contracts\Data\ClientAppData;
use App\Modules\Sap\Contracts\Data\IssuedAppKey;
use App\Modules\Sap\Models\ClientApp;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;
use InvalidArgumentException;
use stdClass;

/**
 * Issues, rotates, finds and revokes app keys. Keys are "bsap_" plus 48
 * random characters; only their SHA-256 and first characters are stored.
 */
final class AppKeys implements ClientAppKeys
{
    /**
     * @throws InvalidArgumentException when the name is empty or another app has it
     */
    public function issue(string $name): IssuedAppKey
    {
        $name = trim($name);

        if ($name === '' || ClientApp::where('nombre', $name)->exists()) {
            throw new InvalidArgumentException("Ya existe una app llamada «{$name}» o el nombre está vacío.");
        }

        $key = $this->newKey();

        $app = ClientApp::create(['nombre' => $name, ...$this->stored($key)]);

        return new IssuedAppKey($app->id, $app->nombre, $key, $app->key_prefix);
    }

    public function revoke(int $appId): void
    {
        ClientApp::whereKey($appId)->whereNull('revoked_at')->update(['revoked_at' => now()]);
    }

    /**
     * Reads the columns one by one, so the key hash never leaves the table.
     */
    public function all(): array
    {
        $timezone = (string) config('app.timezone');
        $time = fn (?string $value): ?CarbonImmutable => $value === null ? null : CarbonImmutable::parse($value, $timezone);

        return DB::table('client_apps')
            ->orderBy('nombre')
            ->get(['id', 'nombre', 'key_prefix', 'created_at', 'last_used_at', 'revoked_at'])
            ->map(fn (stdClass $app): ClientAppData => new ClientAppData(
                id: (int) $app->id,
                name: $app->nombre,
                keyPrefix: $app->key_prefix,
                createdAt: CarbonImmutable::parse($app->created_at, $timezone),
                lastUsedAt: $time($app->last_used_at),
                revokedAt: $time($app->revoked_at),
            ))
            ->values()
            ->all();
    }

    /**
     * Replaces the stored hash in one update, so the old key stops working
     * as soon as it returns.
     */
    public function rotate(int $appId): IssuedAppKey
    {
        $app = ClientApp::find($appId) ?? throw new InvalidArgumentException("No existe la app {$appId}.");
        $key = $this->newKey();

        $app->forceFill([...$this->stored($key), 'revoked_at' => null])->save();

        return new IssuedAppKey($app->id, $app->nombre, $key, $app->key_prefix);
    }

    /**
     * The app of a key that is not revoked. Looked up by hash, so the
     * comparison never depends on the key's characters.
     */
    public function find(string $key): ?ClientApp
    {
        return ClientApp::where('key_hash', hash('sha256', $key))->whereNull('revoked_at')->first();
    }

    private function newKey(): string
    {
        return 'bsap_'.Str::random(48);
    }

    /**
     * What the database keeps of a key.
     *
     * @return array{key_hash: string, key_prefix: string}
     */
    private function stored(string $key): array
    {
        return ['key_hash' => hash('sha256', $key), 'key_prefix' => substr($key, 0, 12)];
    }
}
