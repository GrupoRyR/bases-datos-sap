<?php

namespace App\Models;

use App\Modules\Core\Contracts\Enums\Role;
use Database\Factories\UserFactory;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Attributes\Hidden;
use Illuminate\Database\Eloquent\Casts\Attribute;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Foundation\Auth\User as Authenticatable;
use Illuminate\Notifications\Notifiable;
use Illuminate\Support\Carbon;

/**
 * A person of the TI panel (Core owns the table, see docs/arquitectura.md).
 * They sign in with Microsoft Entra ID only: there is no password.
 *
 * Other modules reference users by id and check access through the Core
 * gates (core.consultar, core.administrar), not by reading the role.
 *
 * @property int $id
 * @property string $name
 * @property string $email
 * @property string|null $microsoft_id
 * @property Role|null $role
 * @property bool $is_active
 * @property Carbon|null $last_signed_in_at
 */
#[Fillable(['name', 'email', 'microsoft_id', 'role', 'is_active'])]
#[Hidden(['remember_token'])]
class User extends Authenticatable
{
    /** @use HasFactory<UserFactory> */
    use HasFactory, Notifiable;

    /**
     * New users are active, as the column default says.
     *
     * @var array<string, mixed>
     */
    protected $attributes = [
        'is_active' => true,
    ];

    /**
     * The e-mail as it is stored: trimmed and in lowercase, so case variants
     * of one address cannot become two people. Use it for lookups too.
     */
    public static function normalizeEmail(string $email): string
    {
        return mb_strtolower(trim($email));
    }

    public function hasRole(Role $role): bool
    {
        return $this->role === $role;
    }

    /**
     * Get the attributes that should be cast.
     *
     * @return array<string, string>
     */
    protected function casts(): array
    {
        return [
            'role' => Role::class,
            'is_active' => 'boolean',
            'last_signed_in_at' => 'datetime',
        ];
    }

    /**
     * Stores every e-mail normalized (see normalizeEmail()).
     *
     * @return Attribute<string, string|null>
     */
    protected function email(): Attribute
    {
        return Attribute::make(
            set: fn (?string $value): ?string => $value === null ? null : self::normalizeEmail($value),
        );
    }
}
