<?php

namespace App\Modules\Core\Application\Auth;

use App\Models\User;
use UnexpectedValueException;

/**
 * Who Microsoft Entra ID says signed in, after the provider validated the
 * response and the id token.
 */
final readonly class MicrosoftIdentity
{
    /**
     * Trimmed and in lowercase (User::normalizeEmail()).
     */
    public string $email;

    /**
     * The display name, or the e-mail when Microsoft sends none.
     */
    public string $name;

    /**
     * @param  string  $objectId  The object id (oid) of the account in Entra ID: users.microsoft_id.
     * @param  string|null  $tenantId  The "tid" claim of the id token; null when absent.
     */
    public function __construct(
        public string $objectId,
        public ?string $tenantId,
        string $email,
        ?string $name = null,
    ) {
        $this->email = User::normalizeEmail($email);
        $this->name = $name === null || trim($name) === '' ? $this->email : trim($name);
    }

    /**
     * From the Microsoft Graph /me profile ("id", "mail", "userPrincipalName",
     * "displayName"): the e-mail is "mail", or the user principal name for
     * accounts without a mailbox.
     *
     * @param  array<array-key, mixed>  $profile
     *
     * @throws UnexpectedValueException When the profile has no object id or no e-mail.
     */
    public static function fromGraph(array $profile, ?string $tenantId): self
    {
        $objectId = self::text($profile, 'id');
        $email = self::text($profile, 'mail') ?? self::text($profile, 'userPrincipalName');

        if ($objectId === null || $email === null) {
            throw new UnexpectedValueException('The Microsoft profile has no object id or no e-mail.');
        }

        return new self($objectId, $tenantId, $email, self::text($profile, 'displayName'));
    }

    /**
     * @param  array<array-key, mixed>  $profile
     */
    private static function text(array $profile, string $key): ?string
    {
        $value = $profile[$key] ?? null;

        return is_string($value) && trim($value) !== '' ? $value : null;
    }
}
