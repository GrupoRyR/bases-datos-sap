<?php

namespace App\Modules\Core\Console;

use App\Models\User;
use App\Modules\Core\Contracts\AuditLogger;
use App\Modules\Core\Contracts\Enums\Role;
use Illuminate\Console\Command;

/**
 * php artisan core:rol <correo> <rol>: gives a role to a user who already
 * signed in with Microsoft, or takes it away with "ninguno". It is how TI
 * manages roles until the panel has a users screen.
 */
final class SetRoleCommand extends Command
{
    private const string NONE = 'ninguno';

    protected $signature = 'core:rol
        {correo : E-mail of a user who already signed in with Microsoft}
        {rol : admin_ti, consulta or ninguno (takes the role away)}';

    protected $description = 'Gives a role of the TI panel to a user, or takes it away';

    public function handle(AuditLogger $audit): int
    {
        $email = User::normalizeEmail((string) $this->argument('correo'));
        $value = trim((string) $this->argument('rol'));
        $role = Role::tryFrom($value);

        if ($role === null && $value !== self::NONE) {
            $this->error("El rol «{$value}» no existe. Usa admin_ti, consulta o ninguno.");

            return self::FAILURE;
        }

        $user = User::query()->where('email', $email)->first();

        if ($user === null) {
            $this->error("No hay ningún usuario con el correo {$email}. Primero tiene que entrar una vez con Microsoft.");

            return self::FAILURE;
        }

        $old = $user->role;

        if ($old === $role) {
            $this->info($role === null
                ? "{$email} ya no tenía rol. No cambió nada."
                : "{$email} ya tenía el rol «{$role->label()}». No cambió nada.");

            return self::SUCCESS;
        }

        $user->role = $role;
        $user->save();

        $audit->record('core.user.role_changed', 'user', $user->id, [
            'old' => $old?->value,
            'new' => $role?->value,
            'source' => 'console',
        ]);

        $this->info($role === null
            ? "Listo: {$email} ya no tiene rol."
            : "Listo: {$email} ahora tiene el rol «{$role->label()}».");

        return self::SUCCESS;
    }
}
