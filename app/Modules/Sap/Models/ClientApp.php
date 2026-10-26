<?php

namespace App\Modules\Sap\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Support\Carbon;

/**
 * An app allowed to ask for updates (table client_apps).
 *
 * @property int $id
 * @property string $nombre
 * @property string $key_hash
 * @property string $key_prefix
 * @property Carbon|null $revoked_at
 * @property Carbon|null $last_used_at
 */
final class ClientApp extends Model
{
    protected $table = 'client_apps';

    protected $guarded = [];

    protected $hidden = ['key_hash'];

    protected function casts(): array
    {
        return [
            'revoked_at' => 'datetime',
            'last_used_at' => 'datetime',
        ];
    }
}
