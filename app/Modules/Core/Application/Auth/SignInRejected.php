<?php

namespace App\Modules\Core\Application\Auth;

use RuntimeException;

/**
 * SignInWithMicrosoft turned the account away. The message is for logs; the
 * user sees __($exception->reason->messageKey()).
 */
final class SignInRejected extends RuntimeException
{
    public function __construct(public readonly RejectionReason $reason)
    {
        parent::__construct("Microsoft sign-in rejected: {$reason->value}.");
    }
}
