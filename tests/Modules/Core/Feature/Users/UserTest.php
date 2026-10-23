<?php

use App\Models\User;
use App\Modules\Core\Contracts\Enums\Role;
use Illuminate\Database\UniqueConstraintViolationException;
use Illuminate\Support\Facades\Schema;
use Tests\Modules\Core\Support\Environment;

it('keeps users on the app connection, without any password column', function () {
    expect(Schema::connection('app')->getColumnListing('users'))->toEqualCanonicalizing([
        'id', 'name', 'email', 'microsoft_id', 'role', 'is_active', 'last_signed_in_at',
        'remember_token', 'created_at', 'updated_at',
    ])
        ->and(Schema::connection('app')->hasTable('password_reset_tokens'))->toBeFalse()
        ->and(Schema::connection('app')->hasTable('sessions'))->toBeTrue();
});

it('normalizes e-mails: trimmed and in lowercase', function () {
    expect(User::normalizeEmail('  Ana.Gomez@Segurex.COM '))->toBe('ana.gomez@segurex.com');
});

it('stores every e-mail normalized', function () {
    $user = User::factory()->create(['email' => ' Ana.Gomez@Segurex.com']);

    expect($user->refresh()->email)->toBe('ana.gomez@segurex.com');
});

it('keeps e-mails and Microsoft ids unique', function (array $first, array $second) {
    User::factory()->create($first);

    expect(fn () => User::factory()->create($second))->toThrow(UniqueConstraintViolationException::class);
})->with([
    'e-mail in another case' => [['email' => 'ana@segurex.com'], ['email' => 'ANA@segurex.com']],
    'Microsoft id' => [['microsoft_id' => 'oid-ana'], ['microsoft_id' => 'oid-ana']],
]);

it('allows many users without a Microsoft id yet', function () {
    User::factory()->count(2)->create(['microsoft_id' => null]);

    expect(User::query()->whereNull('microsoft_id')->count())->toBe(2);
});

it('starts active and without a role', function () {
    $user = User::query()->create(['name' => 'Ana Gómez', 'email' => 'ana@segurex.com']);

    expect($user->is_active)->toBeTrue()
        ->and($user->role)->toBeNull()
        ->and($user->refresh()->is_active)->toBeTrue()
        ->and($user->role)->toBeNull()
        ->and($user->last_signed_in_at)->toBeNull();
});

it('never takes the role or the active flag from mass assignment', function () {
    $user = User::query()->create([
        'name' => 'Ana Gómez',
        'email' => 'ana@segurex.com',
        'role' => Role::AdminTi->value,
        'is_active' => false,
    ]);

    expect($user->refresh()->role)->toBeNull()
        ->and($user->is_active)->toBeTrue();
});

it('casts the role to the Role enum and answers hasRole()', function () {
    $admin = User::factory()->adminTi()->create();
    $reader = User::factory()->consulta()->create();

    expect($admin->refresh()->role)->toBe(Role::AdminTi)
        ->and($admin->hasRole(Role::AdminTi))->toBeTrue()
        ->and($admin->hasRole(Role::Consulta))->toBeFalse()
        ->and($reader->refresh()->role)->toBe(Role::Consulta)
        ->and(User::factory()->create()->hasRole(Role::Consulta))->toBeFalse()
        ->and(User::factory()->inactive()->create()->refresh()->is_active)->toBeFalse();
});

it('reads the bootstrap admins from CORE_ADMIN_EMAILS, trimmed, in lowercase and without empties', function () {
    Environment::with(['CORE_ADMIN_EMAILS' => ' TI@Segurex.com, ,soporte@segurex.com,, '], function () {
        $this->refreshApplication();

        expect(config('core.admins'))->toBe(['ti@segurex.com', 'soporte@segurex.com']);
    });
});

it('has no bootstrap admins when CORE_ADMIN_EMAILS is empty', function () {
    Environment::with(['CORE_ADMIN_EMAILS' => ''], function () {
        $this->refreshApplication();

        expect(config('core.admins'))->toBe([]);
    });
});
