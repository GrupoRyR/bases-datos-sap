<?php

namespace Tests\Modules\Panel\Support;

use App\Modules\Sap\Contracts\ClientAppKeys;
use App\Modules\Sap\Contracts\Data\ClientAppData;
use App\Modules\Sap\Contracts\Data\IssuedAppKey;
use Carbon\CarbonImmutable;
use InvalidArgumentException;

/**
 * ClientAppKeys kept in memory, with the same rules as the real one: a name
 * is unique (revoked apps included), rotating revives a revoked app and an
 * unknown app throws. Keys are predictable ("bsap_" plus the app id and a
 * counter, padded) and every call is recorded, so panel tests never touch
 * the Sap tables.
 */
final class FakeClientAppKeys implements ClientAppKeys
{
    /** @var list<array{method: string, argument: int|string}> */
    public array $calls = [];

    /** @var list<string> Every full key handed out, to prove none leaks. */
    public array $keys = [];

    /** @var array<int, ClientAppData> */
    private array $apps = [];

    private int $nextId = 1;

    public function issue(string $name): IssuedAppKey
    {
        $this->calls[] = ['method' => 'issue', 'argument' => $name];
        $name = trim($name);

        $taken = array_filter($this->apps, fn (ClientAppData $app): bool => $app->name === $name) !== [];

        if ($name === '' || $taken) {
            throw new InvalidArgumentException("Ya existe una app llamada «{$name}» o el nombre está vacío.");
        }

        $id = $this->nextId++;
        $key = $this->newKey($id);
        $this->apps[$id] = new ClientAppData($id, $name, substr($key, 0, 12), CarbonImmutable::now(), null, null);

        return new IssuedAppKey($id, $name, $key, substr($key, 0, 12));
    }

    public function revoke(int $appId): void
    {
        $this->calls[] = ['method' => 'revoke', 'argument' => $appId];
        $app = $this->apps[$appId] ?? null;

        if ($app !== null && $app->revokedAt === null) {
            $this->apps[$appId] = new ClientAppData($app->id, $app->name, $app->keyPrefix, $app->createdAt, $app->lastUsedAt, CarbonImmutable::now());
        }
    }

    public function all(): array
    {
        $apps = array_values($this->apps);
        usort($apps, fn (ClientAppData $a, ClientAppData $b): int => strcmp($a->name, $b->name));

        return $apps;
    }

    public function rotate(int $appId): IssuedAppKey
    {
        $this->calls[] = ['method' => 'rotate', 'argument' => $appId];
        $app = $this->apps[$appId] ?? throw new InvalidArgumentException("No existe la app {$appId}.");
        $key = $this->newKey($appId);

        $this->apps[$appId] = new ClientAppData($app->id, $app->name, substr($key, 0, 12), $app->createdAt, $app->lastUsedAt, null);

        return new IssuedAppKey($app->id, $app->name, $key, substr($key, 0, 12));
    }

    /**
     * An app as the panel would find it, with its times read in Bogota.
     */
    public function add(string $name, string $createdAt = '2026-10-01 08:00', ?string $lastUsedAt = null, ?string $revokedAt = null): ClientAppData
    {
        $id = $this->nextId++;
        $key = $this->newKey($id);
        $time = fn (?string $value): ?CarbonImmutable => $value === null ? null : CarbonImmutable::parse($value, 'America/Bogota');

        return $this->apps[$id] = new ClientAppData($id, $name, substr($key, 0, 12), CarbonImmutable::parse($createdAt, 'America/Bogota'), $time($lastUsedAt), $time($revokedAt));
    }

    private function newKey(int $appId): string
    {
        $key = 'bsap_'.str_pad($appId.'k'.count($this->keys), 7, '0', STR_PAD_LEFT).str_repeat('s3cr3t', 7);
        $this->keys[] = $key;

        return $key;
    }
}
