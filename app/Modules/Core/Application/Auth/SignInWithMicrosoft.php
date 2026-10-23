<?php

namespace App\Modules\Core\Application\Auth;

use App\Models\User;
use App\Modules\Core\Contracts\AuditLogger;
use App\Modules\Core\Contracts\Enums\Role;
use Illuminate\Contracts\Config\Repository as Config;
use Illuminate\Database\ConnectionInterface;

/**
 * Turns the identity Microsoft sent back into the user who signs in.
 *
 * 1. The "tid" claim must be the configured tenant.
 * 2. The user is found by Microsoft object id, else by e-mail. An account
 *    that belongs to another user, an e-mail linked to another account and
 *    a deactivated user are turned away; an unknown e-mail becomes a new
 *    user without a role.
 * 3. The Microsoft id, the name and the time of the sign-in are stored.
 * 4. An e-mail listed in core.admins (CORE_ADMIN_EMAILS) gets admin_ti.
 *    Nobody is ever downgraded here.
 *
 * Steps 2 to 4 run in one transaction. Every change and every rejection goes
 * to the audit log; tokens never do. The controller audits the sign-in
 * itself once the user is signed in, so the entry names them as the actor.
 */
final class SignInWithMicrosoft
{
    public function __construct(
        private readonly AuditLogger $audit,
        private readonly ConnectionInterface $database,
        private readonly Config $config,
    ) {}

    /**
     * @throws SignInRejected When the account may not sign in.
     */
    public function handle(MicrosoftIdentity $identity): User
    {
        try {
            $this->ensureConfiguredTenant($identity);

            return $this->database->transaction(fn (): User => $this->signIn($identity));
        } catch (SignInRejected $rejected) {
            // After the rollback, so the entry stays.
            $this->audit->record('core.auth.rejected', context: [
                'reason' => $rejected->reason->value,
                'email' => $identity->email,
            ]);

            throw $rejected;
        }
    }

    /**
     * Fails closed: without a configured tenant nobody signs in. Tenant ids
     * are GUIDs, which compare without regard to case.
     */
    private function ensureConfiguredTenant(MicrosoftIdentity $identity): void
    {
        $configured = $this->config->get('services.microsoft.tenant');
        $tenant = is_string($configured) ? trim($configured) : '';

        if ($tenant === '' || $identity->tenantId === null || strcasecmp($tenant, $identity->tenantId) !== 0) {
            throw new SignInRejected(RejectionReason::Tenant);
        }
    }

    private function signIn(MicrosoftIdentity $identity): User
    {
        $byAccount = User::query()->where('microsoft_id', $identity->objectId)->lockForUpdate()->first();
        $byEmail = User::query()->where('email', $identity->email)->lockForUpdate()->first();

        // The account is linked to someone else than the e-mail's owner, or
        // the e-mail's owner is linked to another account.
        if (($byAccount !== null && $byEmail !== null && ! $byAccount->is($byEmail))
            || ($byAccount === null && $byEmail?->microsoft_id !== null)) {
            throw new SignInRejected(RejectionReason::IdentityMismatch);
        }

        $user = $byAccount ?? $byEmail;

        if ($user !== null && ! $user->is_active) {
            throw new SignInRejected(RejectionReason::Inactive);
        }

        $user ??= $this->createUser($identity);

        $user->forceFill([
            'microsoft_id' => $identity->objectId,
            'name' => $identity->name,
            'last_signed_in_at' => now(),
        ])->save();

        $this->promoteBootstrapAdmin($user, $identity);

        return $user;
    }

    private function createUser(MicrosoftIdentity $identity): User
    {
        $user = User::query()->create([
            'name' => $identity->name,
            'email' => $identity->email,
            'microsoft_id' => $identity->objectId,
        ]);

        $this->audit->record('core.user.created', 'user', $user->id, [
            'email' => $user->email,
            'source' => 'microsoft',
        ]);

        return $user;
    }

    /**
     * The first admins come from CORE_ADMIN_EMAILS, so they need no console.
     * The e-mail is the one Microsoft vouches for in this sign-in.
     */
    private function promoteBootstrapAdmin(User $user, MicrosoftIdentity $identity): void
    {
        $admins = $this->config->get('core.admins', []);

        if ($user->hasRole(Role::AdminTi) || ! is_array($admins) || ! in_array($identity->email, $admins, true)) {
            return;
        }

        $old = $user->role;
        $user->role = Role::AdminTi;
        $user->save();

        $this->audit->record('core.user.role_changed', 'user', $user->id, [
            'old' => $old?->value,
            'new' => Role::AdminTi->value,
            'source' => 'core_admin_emails',
        ]);
    }
}
