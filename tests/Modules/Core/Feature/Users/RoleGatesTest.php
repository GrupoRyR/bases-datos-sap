<?php

use App\Models\User;
use Illuminate\Support\Facades\Gate;

/**
 * A user factory with the given role state (none for null).
 */
function userWith(?string $state): User
{
    return $state === null ? User::factory()->create() : User::factory()->{$state}()->create();
}

it('lets any active user with a role consult', function (?string $state, bool $allowed) {
    $user = userWith($state);

    expect(Gate::forUser($user)->allows('core.consultar'))->toBe($allowed);
})->with([
    'admin TI' => ['adminTi', true],
    'consulta' => ['consulta', true],
    'no role' => [null, false],
]);

it('lets only admin TI administer', function (?string $state, bool $allowed) {
    $user = userWith($state);

    expect(Gate::forUser($user)->allows('core.administrar'))->toBe($allowed);
})->with([
    'admin TI' => ['adminTi', true],
    'consulta' => ['consulta', false],
    'no role' => [null, false],
]);

it('lets an inactive user do nothing, whatever their role', function () {
    $admin = User::factory()->adminTi()->inactive()->create();

    expect(Gate::forUser($admin)->allows('core.consultar'))->toBeFalse()
        ->and(Gate::forUser($admin)->allows('core.administrar'))->toBeFalse();
});

it('lets guests do nothing', function () {
    expect(Gate::allows('core.consultar'))->toBeFalse()
        ->and(Gate::allows('core.administrar'))->toBeFalse();
});
