<?php

use App\Models\User;
use App\Modules\Core\Contracts\AuditLogger;
use App\Modules\Core\Infrastructure\Audit\DatabaseAuditLogger;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Route;

/**
 * The only row of audit_logs, with its context decoded.
 *
 * @return array<string, mixed>
 */
function soleAuditRow(): array
{
    $row = (array) DB::table('audit_logs')->sole();
    $row['context'] = $row['context'] === null ? null : json_decode((string) $row['context'], true);

    return $row;
}

beforeEach(function () {
    // Records one entry from inside a real HTTP request.
    Route::middleware(['web', 'auth'])->get('/_test/auditoria', function (AuditLogger $audit) {
        $audit->record('core.user.role_changed', 'user', 7, ['old' => null, 'new' => 'consulta']);

        return response()->noContent();
    });
});

it('is the AuditLogger of the container', function () {
    expect(app(AuditLogger::class))->toBeInstanceOf(DatabaseAuditLogger::class);
});

it('records the signed-in user and the IP address of the request', function () {
    $this->freezeSecond();
    $user = User::factory()->create();

    $this->actingAs($user)
        ->withServerVariables(['REMOTE_ADDR' => '203.0.113.9'])
        ->get('/_test/auditoria')
        ->assertNoContent();

    $row = soleAuditRow();

    expect(array_keys($row))->toEqualCanonicalizing(['id', 'user_id', 'action', 'subject_type', 'subject_id', 'context', 'ip', 'created_at'])
        ->and($row['action'])->toBe('core.user.role_changed')
        ->and($row['subject_type'])->toBe('user')
        ->and($row['subject_id'])->toBe('7')
        ->and($row['context'])->toBe(['old' => null, 'new' => 'consulta'])
        ->and((int) $row['user_id'])->toBe($user->id)
        ->and($row['ip'])->toBe('203.0.113.9')
        ->and(Carbon::parse($row['created_at'])->equalTo(now()))->toBeTrue();
});

it('records actions of the system without a user, an IP address or a context', function () {
    app(AuditLogger::class)->record('core.robot.run_closed');

    $row = soleAuditRow();

    expect($row['user_id'])->toBeNull()
        ->and($row['ip'])->toBeNull()
        ->and($row['subject_type'])->toBeNull()
        ->and($row['subject_id'])->toBeNull()
        ->and($row['context'])->toBeNull();
});

it('stores the subject id as a string', function (int|string $id, string $stored) {
    app(AuditLogger::class)->record('sap.request.created', 'request', $id);

    expect(soleAuditRow()['subject_id'])->toBe($stored);
})->with([
    'int id' => [42, '42'],
    'string id' => ['SGX-C-0042', 'SGX-C-0042'],
]);

it('never stores values whose keys look like secrets, at any depth', function () {
    app(AuditLogger::class)->record('core.app.key_created', 'app', 3, [
        'name' => 'Gestor de cartera',
        'api_token' => 'abc',
        'nested' => ['client_secret' => 'xyz', 'Password' => 'p', 'kept' => 1],
    ]);

    expect(soleAuditRow()['context'])->toBe([
        'name' => 'Gestor de cartera',
        'api_token' => '[redacted]',
        'nested' => ['client_secret' => '[redacted]', 'Password' => '[redacted]', 'kept' => 1],
    ]);
});

it('refuses an action that does not follow <module>.<entity>.<verb>', function (string $action) {
    expect(fn () => app(AuditLogger::class)->record($action))
        ->toThrow(InvalidArgumentException::class);

    expect(DB::table('audit_logs')->count())->toBe(0);
})->with(['two segments' => ['core.login'], 'uppercase' => ['Core.User.Created'], 'spaces' => ['core.user. created']]);
