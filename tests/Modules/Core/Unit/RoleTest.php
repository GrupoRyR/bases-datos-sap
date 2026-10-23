<?php

use App\Modules\Core\Contracts\Enums\Role;

it('has exactly the two roles of the TI panel, stored by value', function () {
    expect(array_column(Role::cases(), 'value'))->toBe(['admin_ti', 'consulta']);
});

it('labels each role in Spanish', function (Role $role, string $label) {
    expect($role->label())->toBe($label);
})->with([
    'admin TI' => [Role::AdminTi, 'Admin TI'],
    'consulta' => [Role::Consulta, 'Consulta'],
]);
