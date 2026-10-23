<?php

namespace App\Modules\Core\Database\Seeders;

use App\Models\User;
use App\Modules\Core\Contracts\Enums\Role;
use Illuminate\Database\Seeder;

/**
 * Demo users for the local-only demo sign-in (/dev/entrar). DatabaseSeeder
 * runs it only in local; it also refuses to run anywhere else. The
 * example.test domain can never be a real Microsoft account.
 */
final class CoreDemoSeeder extends Seeder
{
    public function run(): void
    {
        if (! app()->isLocal()) {
            return;
        }

        foreach ([
            'admin-ti@example.test' => ['Admin TI de prueba', Role::AdminTi],
            'consulta@example.test' => ['Consulta de prueba', Role::Consulta],
        ] as $email => [$name, $role]) {
            // forceFill: role and is_active are never mass-assignable (User),
            // and this seeder may run outside db:seed's unguarded wrapper.
            User::query()->firstOrNew(['email' => $email])
                ->forceFill(['name' => $name, 'role' => $role, 'is_active' => true])
                ->save();
        }
    }
}
