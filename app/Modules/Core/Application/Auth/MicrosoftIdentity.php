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
     * @param  bool  $guest  A guest (B2B) account of the tenant, not a member.
     */
    public function __construct(
        public string $objectId,
        public ?string $tenantId,
        string $email,
        ?string $name = null,
        public bool $guest = false,
    ) {
        $this->email = User::normalizeEmail($email);
        $this->name = $name === null || trim($name) === '' ? $this->email : trim($name);
    }

    /**
     * From the Microsoft Graph /me profile ("id", "mail", "userPrincipalName",
     * "displayName"): the e-mail is "mail", or the user principal name for
     * accounts without a mailbox.
     *
     * A guest is one the id token says is ("acct" claim 1, which Entra ID
     * sends only when the app registration asks for it) or whose user
     * principal name carries the "#EXT#" Entra ID gives every invited
     * account, so guests are caught without that claim too.
     *
     * @param  array<array-key, mixed>  $profile
     *
     * @throws UnexpectedValueException When the profile has no object id or no e-mail.
     */
    public static function fromGraph(array $profile, ?string $tenantId, bool $guestClaim = false): self
    {
        $objectId = self::text($profile, 'id');
        $principalName = self::text($profile, 'userPrincipalName');
        $email = self::text($profile, 'mail') ?? $principalName;

        if ($objectId === null || $email === null) {
            throw new UnexpectedValueException('The Microsoft profile has no object id or no e-mail.');
        }

        $guest = $guestClaim || ($principalName !== null && stripos($principalName, '#EXT#') !== false);

        return new self($objectId, $tenantId, $email, self::text($profile, 'displayName'), $guest);
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
