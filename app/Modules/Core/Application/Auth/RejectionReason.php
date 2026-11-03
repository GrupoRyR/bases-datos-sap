<?php

namespace App\Modules\Core\Application\Auth;

/**
 * Why SignInWithMicrosoft turned a Microsoft account away. The value goes to
 * the audit log (context "reason"). The user sees one message for every
 * reason but Guest, so the sign-in page tells nothing about other people's
 * accounts; a guest is only told about their own kind of account.
 */
enum RejectionReason: string
{
    /** The "tid" claim is missing or is not the configured tenant (or none is configured). */
    case Tenant = 'tenant';

    /** A guest (B2B) account of the tenant, not a member. */
    case Guest = 'guest';

    /** The Microsoft account belongs to another user, or the e-mail to another Microsoft account. */
    case IdentityMismatch = 'identity_mismatch';

    /** The user was deactivated. */
    case Inactive = 'inactive';

    /**
     * The translation key of the message the sign-in page shows.
     */
    public function messageKey(): string
    {
        return match ($this) {
            self::Guest => 'core::ingreso.invitado',
            default => 'core::ingreso.rechazado',
        };
    }
}
