<?php

namespace App\Modules\Core\Infrastructure\Audit;

use App\Modules\Core\Contracts\AuditLogger;
use Illuminate\Contracts\Auth\Factory as AuthFactory;
use Illuminate\Contracts\Foundation\Application;
use Illuminate\Database\ConnectionInterface;
use Illuminate\Http\Request;
use InvalidArgumentException;

/**
 * AuditLogger that appends each entry to "audit_logs" on the app connection.
 *
 * The actor is the user signed in on the default guard, or nobody (the
 * system) in console commands, jobs and robot calls. The IP address comes
 * from the HTTP request being handled, if any. Keys that look like secrets
 * are redacted as a safety net, although the contract already forbids them.
 */
final class DatabaseAuditLogger implements AuditLogger
{
    /**
     * "<module-key>.<entity>.<verb>": three or more lowercase snake_case segments.
     */
    private const string ACTION = '/^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){2,}$/';

    /**
     * Keys whose values are never stored, at any depth.
     */
    private const string SECRET_KEY = '/password|secret|token/i';

    private const string REDACTED = '[redacted]';

    public function __construct(
        private readonly AuthFactory $auth,
        private readonly Application $app,
        private readonly ConnectionInterface $database,
    ) {}

    public function record(
        string $action,
        ?string $subjectType = null,
        int|string|null $subjectId = null,
        array $context = [],
    ): void {
        if (preg_match(self::ACTION, $action) !== 1) {
            throw new InvalidArgumentException("Audit action [{$action}] must look like <module-key>.<entity>.<verb>, e.g. core.user.role_changed.");
        }

        $this->database->table('audit_logs')->insert([
            'user_id' => $this->auth->guard()->id(),
            'action' => $action,
            'subject_type' => $subjectType,
            'subject_id' => $subjectId === null ? null : (string) $subjectId,
            'context' => $context === [] ? null : json_encode($this->redact($context), JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE),
            'ip' => $this->request()?->ip(),
            'created_at' => now(),
        ]);
    }

    /**
     * The HTTP request being handled. Console commands also have a
     * "request" (made up by SetRequestForConsole), but it never goes through
     * the router; HTTP tests run in the console too, so a routed request is
     * what tells them apart there.
     */
    private function request(): ?Request
    {
        $request = $this->app->bound('request') ? $this->app->make('request') : null;

        if (! $request instanceof Request) {
            return null;
        }

        return ! $this->app->runningInConsole() || $request->route() !== null ? $request : null;
    }

    /**
     * @param  array<array-key, mixed>  $values
     * @return array<array-key, mixed>
     */
    private function redact(array $values): array
    {
        foreach ($values as $key => $value) {
            if (is_string($key) && preg_match(self::SECRET_KEY, $key) === 1) {
                $values[$key] = self::REDACTED;
            } elseif (is_array($value)) {
                $values[$key] = $this->redact($value);
            }
        }

        return $values;
    }
}
