<?php

use App\Models\User;
use App\Modules\Core\Contracts\Enums\Role;
use App\Modules\Core\Database\Seeders\CoreDemoSeeder;
use Database\Seeders\DatabaseSeeder;

it('creates no demo users outside local', function () {
    $this->seed(DatabaseSeeder::class);
    $this->seed(CoreDemoSeeder::class);

    expect(User::query()->count())->toBe(0);
});

it('creates an admin TI and a consulta demo user in local, only with example.test e-mails', function () {
    $this->app['env'] = 'local';

    $this->seed(DatabaseSeeder::class);

    $users = User::query()->orderBy('name')->get();

    expect($users->pluck('name')->all())->toBe(['Admin TI de prueba', 'Consulta de prueba'])
        ->and($users->pluck('role')->all())->toBe([Role::AdminTi, Role::Consulta])
        ->and($users->every(fn (User $user): bool => $user->is_active && $user->microsoft_id === null))->toBeTrue()
        ->and($users->every(fn (User $user): bool => str_ends_with($user->email, '@example.test')))->toBeTrue();
});

it('can run again without duplicating the demo users', function () {
    $this->app['env'] = 'local';

    $this->seed(CoreDemoSeeder::class);
    $this->seed(CoreDemoSeeder::class);

    expect(User::query()->count())->toBe(2);
});
