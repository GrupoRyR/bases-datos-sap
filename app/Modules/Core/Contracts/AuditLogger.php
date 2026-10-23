<?php

namespace App\Modules\Core\Contracts;

use InvalidArgumentException;

/**
 * The append-only audit log of the app: who did what, to what, from where.
 *
 * Implemented by Core (Infrastructure\Audit\DatabaseAuditLogger). The
 * implementation adds the signed-in user (none for the system: robot,
 * console, scheduler), the IP address of the request and the time itself.
 * Entries are never updated or deleted.
 */
interface AuditLogger
{
    /**
     * Records one auditable action.
     *
     * @param  string  $action  "<module-key>.<entity>.<verb>" in lowercase snake_case segments,
     *                          e.g. "core.user.role_changed" or "sap.request.created".
     * @param  string|null  $subjectType  Kind of the affected record, e.g. "user" or "request".
     * @param  int|string|null  $subjectId  Id of the affected record.
     * @param  array<string, mixed>  $context  JSON-encodable details, e.g. the old and new role.
     *                                         Never include secrets, tokens or passwords.
     *
     * @throws InvalidArgumentException When $action does not follow the naming pattern.
     */
    public function record(
        string $action,
        ?string $subjectType = null,
        int|string|null $subjectId = null,
        array $context = [],
    ): void;
}
