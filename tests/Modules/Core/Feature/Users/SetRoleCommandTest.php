<?php

use App\Models\User;
use App\Modules\Core\Contracts\Enums\Role;
use Illuminate\Support\Facades\DB;

/**
 * The role_changed entries of audit_logs, with their context decoded.
 *
 * @return list<array<string, mixed>>
 */
function roleChanges(): array
{
    return DB::table('audit_logs')
        ->where('action', 'core.user.role_changed')
        ->orderBy('id')
        ->get()
        ->map(fn (object $row): array => [
            'subject_type' => $row->subject_type,
            'subject_id' => $row->subject_id,
            'user_id' => $row->user_id,
            'context' => json_decode((string) $row->context, true),
        ])
        ->all();
}

it('gives a role to an existing user, by e-mail in any case, and audits it', function () {
    $user = User::factory()->create(['email' => 'ana.gomez@segurex.com']);

    $this->artisan('core:rol', ['correo' => ' Ana.Gomez@Segurex.com ', 'rol' => 'admin_ti'])
        ->expectsOutputToContain('ana.gomez@segurex.com ahora tiene el rol «Admin TI»')
        ->assertSuccessful();

    expect($user->refresh()->role)->toBe(Role::AdminTi)
        ->and(roleChanges())->toEqual([[
            'subject_type' => 'user',
            'subject_id' => (string) $user->id,
            'user_id' => null,
            'context' => ['old' => null, 'new' => 'admin_ti', 'source' => 'console'],
        ]]);
});

it('changes one role for the other', function () {
    $user = User::factory()->adminTi()->create(['email' => 'ana@segurex.com']);

    $this->artisan('core:rol', ['correo' => 'ana@segurex.com', 'rol' => 'consulta'])->assertSuccessful();

    expect($user->refresh()->role)->toBe(Role::Consulta)
        ->and(roleChanges()[0]['context'])->toEqual(['old' => 'admin_ti', 'new' => 'consulta', 'source' => 'console']);
});

it('takes the role away with "ninguno"', function () {
    $user = User::factory()->consulta()->create(['email' => 'ana@segurex.com']);

    $this->artisan('core:rol', ['correo' => 'ana@segurex.com', 'rol' => 'ninguno'])
        ->expectsOutputToContain('ana@segurex.com ya no tiene rol')
        ->assertSuccessful();

    expect($user->refresh()->role)->toBeNull()
        ->and(roleChanges()[0]['context'])->toEqual(['old' => 'consulta', 'new' => null, 'source' => 'console']);
});

it('says so and audits nothing when the user already has that role', function () {
    $user = User::factory()->consulta()->create(['email' => 'ana@segurex.com']);

    $this->artisan('core:rol', ['correo' => 'ana@segurex.com', 'rol' => 'consulta'])
        ->expectsOutputToContain('ya tenía el rol «Consulta»')
        ->assertSuccessful();

    expect($user->refresh()->role)->toBe(Role::Consulta)
        ->and(roleChanges())->toBe([]);
});

it('fails with a clear message for an unknown e-mail', function () {
    $this->artisan('core:rol', ['correo' => 'nadie@segurex.com', 'rol' => 'consulta'])
        ->expectsOutputToContain('No hay ningún usuario con el correo nadie@segurex.com')
        ->assertFailed();

    expect(roleChanges())->toBe([]);
});

it('fails with a clear message for an unknown role, and changes nothing', function (string $role) {
    $user = User::factory()->consulta()->create(['email' => 'ana@segurex.com']);

    $this->artisan('core:rol', ['correo' => 'ana@segurex.com', 'rol' => $role])
        ->expectsOutputToContain('Usa admin_ti, consulta o ninguno')
        ->assertFailed();

    expect($user->refresh()->role)->toBe(Role::Consulta)
        ->and(roleChanges())->toBe([]);
})->with(['unknown' => ['jefe'], 'label instead of value' => ['Admin TI'], 'empty' => ['']]);
