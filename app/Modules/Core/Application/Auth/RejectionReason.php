<?php

namespace App\Modules\Core\Application\Auth;

/**
 * Why SignInWithMicrosoft turned a Microsoft account away. The value goes to
 * the audit log (context "reason"); the user always sees the same message,
 * so the sign-in page tells nothing about other people's accounts.
 */
enum RejectionReason: string
{
    /** The "tid" claim is missing or is not the configured tenant (or none is configured). */
    case Tenant = 'tenant';

    /** The Microsoft account belongs to another user, or the e-mail to another Microsoft account. */
    case IdentityMismatch = 'identity_mismatch';

    /** The user was deactivated. */
    case Inactive = 'inactive';
}
