<?php

use App\Modules\Sap\Contracts\ClientAppKeys;
use App\Modules\Sap\Contracts\Data\ClientAppData;
use Illuminate\Support\Facades\DB;

/*
| The app keys the panel lists and rotates through Contracts\ClientAppKeys
| (docs/contrato-robot.md, section 7.4).
*/

beforeEach(function () {
    $this->travelTo(now()->setDate(2026, 10, 27)->setTime(10, 0));
});

/** @return array<string, string> */
function keysBearer(string $key): array
{
    return ['Authorization' => "Bearer {$key}"];
}

it('lists every app by name, revoked ones included, without the key hash', function () {
    $keys = app(ClientAppKeys::class);
    $orders = $keys->issue('Toma de pedidos');
    $portfolio = $keys->issue('Gestor de cartera');
    $keys->revoke($orders->id);

    $apps = $keys->all();

    expect(array_map(fn (ClientAppData $app): string => $app->name, $apps))->toBe(['Gestor de cartera', 'Toma de pedidos'])
        ->and($apps[0]->id)->toBe($portfolio->id)
        ->and($apps[0]->keyPrefix)->toBe(substr($portfolio->key, 0, 12))
        ->and($apps[0]->createdAt->format('Y-m-d H:i'))->toBe('2026-10-27 10:00')
        ->and($apps[0]->lastUsedAt)->toBeNull()
        ->and($apps[0]->revokedAt)->toBeNull()
        ->and($apps[1]->revokedAt?->format('H:i'))->toBe('10:00')
        ->and(array_keys(get_object_vars($apps[0])))->toBe(['id', 'name', 'keyPrefix', 'createdAt', 'lastUsedAt', 'revokedAt']);
});

it('rotates a key: the old one gets 401 at once and the new one works', function () {
    $keys = app(ClientAppKeys::class);
    $old = $keys->issue('Gestor de cartera');

    $new = $keys->rotate($old->id);

    expect($new->id)->toBe($old->id)
        ->and($new->name)->toBe('Gestor de cartera')
        ->and($new->key)->toStartWith('bsap_')->not->toBe($old->key)
        ->and(DB::table('client_apps')->value('key_hash'))->toBe(hash('sha256', $new->key))
        ->and(DB::table('client_apps')->value('key_prefix'))->toBe(substr($new->key, 0, 12));

    $this->getJson('/api/v1/estado?empresa=SGX&conjunto=CARTERA', keysBearer($old->key))->assertUnauthorized();
    $this->getJson('/api/v1/estado?empresa=SGX&conjunto=CARTERA', keysBearer($new->key))->assertOk();
});

it('brings a revoked app back with its new key', function () {
    $keys = app(ClientAppKeys::class);
    $old = $keys->issue('Gestor de cartera');
    $keys->revoke($old->id);

    $new = $keys->rotate($old->id);

    expect($keys->all()[0]->revokedAt)->toBeNull();
    $this->getJson('/api/v1/estado?empresa=SGX&conjunto=CARTERA', keysBearer($new->key))->assertOk();
});

it('refuses to rotate an unknown app', function () {
    app(ClientAppKeys::class)->rotate(999);
})->throws(InvalidArgumentException::class);
