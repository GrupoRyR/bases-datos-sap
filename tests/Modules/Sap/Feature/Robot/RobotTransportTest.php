<?php

use App\Modules\Sap\Domain\Robot\RobotSignature;
use App\Modules\Sap\Infrastructure\Robot\NonceStore;
use Illuminate\Http\Request;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Route;
use Tests\Modules\Sap\Support\RobotClient;

/*
| Transport and signature of every robot request (docs/contrato-robot.md,
| sections 2 and 3), checked on a test route behind the "sap.robot" group.
*/

const ROBOT_TEST_PATH = '/api/robot/v1/_prueba';

beforeEach(function () {
    RobotClient::configure();

    // Echoes what the endpoint receives after the middleware.
    Route::post(ltrim(ROBOT_TEST_PATH, '/'), fn (Request $request) => response()->json([
        'input' => $request->all(),
        'key' => $request->attributes->get('robot_key'),
    ]))->middleware('sap.robot');
});

it('matches the test vector of the contract', function () {
    $body = '{"conjunto":"CARTERA"}';

    expect(hash('sha256', $body))->toBe('c04ff2072e7cfb7c308adf681b5c060ec271b48124895c3310a9a49e912091b9')
        ->and(RobotSignature::sign('robot-secreto-de-prueba', 1792152000, '9f86d081884c7d659a2feaa0c55ad015', '/api/robot/v1/corridas', $body))
        ->toBe('sha256=29d3895ed1dec41dc0c471b2a3e0b148e975b479698a86a13833814b661e0dd2');
});

it('lets a signed request through with its JSON and its key', function () {
    RobotClient::post($this, ROBOT_TEST_PATH, ['conjunto' => 'CARTERA', 'nombre' => 'Ferretería'])
        ->assertOk()
        ->assertExactJson(['input' => ['conjunto' => 'CARTERA', 'nombre' => 'Ferretería'], 'key' => RobotClient::KEY]);
});

it('reads a gzip body signed over the compressed bytes', function () {
    RobotClient::post($this, ROBOT_TEST_PATH, ['conjunto' => 'MAESTROS'], gzip: true)
        ->assertOk()
        ->assertJsonPath('input.conjunto', 'MAESTROS');
});

it('rejects every broken signature with the same 401', function (array $headers) {
    RobotClient::post($this, ROBOT_TEST_PATH, ['conjunto' => 'CARTERA'], headers: $headers)
        ->assertUnauthorized()
        ->assertExactJson(['message' => 'Firma inválida.']);
})->with([
    'no key' => [['X-Robot-Key' => null]],
    'no timestamp' => [['X-Robot-Timestamp' => null]],
    'no nonce' => [['X-Robot-Nonce' => null]],
    'no signature' => [['X-Robot-Signature' => null]],
    'unknown key' => [['X-Robot-Key' => 'otra']],
    'malformed key' => [['X-Robot-Key' => 'r 2026']],
    'timestamp with letters' => [['X-Robot-Timestamp' => '17921520OO']],
    'uppercase nonce' => [['X-Robot-Nonce' => '9F86D081884C7D659A2FEAA0C55AD015']],
    'short nonce' => [['X-Robot-Nonce' => '9f86d081']],
    'signature without prefix' => [['X-Robot-Signature' => str_repeat('a', 64)]],
    'wrong signature' => [['X-Robot-Signature' => 'sha256='.str_repeat('a', 64)]],
]);

it('rejects a body or a path that is not the signed one', function () {
    $timestamp = time();
    $nonce = bin2hex(random_bytes(16));
    $signedFor = fn (string $path, string $body): string => RobotClient::sign(RobotClient::SECRET, $timestamp, $nonce, $path, $body);

    RobotClient::post($this, ROBOT_TEST_PATH, '{"conjunto":"CARTERA"}', timestamp: $timestamp, nonce: $nonce,
        headers: ['X-Robot-Signature' => $signedFor(ROBOT_TEST_PATH, '{"conjunto":"MAESTROS"}')])->assertUnauthorized();

    RobotClient::post($this, ROBOT_TEST_PATH, '{"conjunto":"CARTERA"}', timestamp: $timestamp, nonce: $nonce,
        headers: ['X-Robot-Signature' => $signedFor('/api/robot/v1/corridas', '{"conjunto":"CARTERA"}')])->assertUnauthorized();
});

it('accepts clocks up to 300 seconds apart and rejects anything beyond', function (int $offset, int $status) {
    $this->freezeSecond();

    RobotClient::post($this, ROBOT_TEST_PATH, [], timestamp: now()->getTimestamp() + $offset)->assertStatus($status);
})->with([
    '300 s behind' => [-300, 200],
    '300 s ahead' => [300, 200],
    '301 s behind' => [-301, 401],
    '301 s ahead' => [301, 401],
]);

it('rejects a replayed nonce of the same key', function () {
    $nonce = bin2hex(random_bytes(16));

    RobotClient::post($this, ROBOT_TEST_PATH, [], nonce: $nonce)->assertOk();
    RobotClient::post($this, ROBOT_TEST_PATH, [], nonce: $nonce)->assertUnauthorized();
});

it('accepts the same nonce under another key', function () {
    config(['sap.robot.keys' => RobotClient::KEY.':'.RobotClient::SECRET.', r2027b:otro-secreto-de-prueba']);
    $nonce = bin2hex(random_bytes(16));
    $timestamp = time();

    RobotClient::post($this, ROBOT_TEST_PATH, [], nonce: $nonce)->assertOk();
    RobotClient::post($this, ROBOT_TEST_PATH, [], timestamp: $timestamp, nonce: $nonce, headers: [
        'X-Robot-Key' => 'r2027b',
        'X-Robot-Signature' => RobotClient::sign('otro-secreto-de-prueba', $timestamp, $nonce, ROBOT_TEST_PATH, '{}'),
    ])->assertOk();
});

it('stores a nonce only after the signature checks out', function () {
    $nonce = bin2hex(random_bytes(16));

    // A third party cannot burn the robot's nonce with a forged request.
    RobotClient::post($this, ROBOT_TEST_PATH, [], nonce: $nonce, headers: ['X-Robot-Signature' => 'sha256='.str_repeat('0', 64)])
        ->assertUnauthorized();

    RobotClient::post($this, ROBOT_TEST_PATH, [], nonce: $nonce)->assertOk();
});

it('logs why a signature failed with the key and the IP, never the secret', function () {
    Log::spy();

    RobotClient::post($this, ROBOT_TEST_PATH, [], headers: ['X-Robot-Signature' => 'sha256='.str_repeat('a', 64)]);

    Log::shouldHaveReceived('warning')->once()->withArgs(function (string $message, array $context): bool {
        return $message === 'sap.robot.signature_rejected'
            && $context === ['reason' => 'signature_mismatch', 'key' => RobotClient::KEY, 'ip' => '127.0.0.1']
            && ! str_contains((string) json_encode($context), RobotClient::SECRET);
    });
});

it('answers 413 to a body over 10 MB before looking at the signature', function () {
    RobotClient::post($this, ROBOT_TEST_PATH, str_repeat('a', 10 * 1024 * 1024 + 1), headers: ['X-Robot-Signature' => null])
        ->assertStatus(413)
        ->assertJsonPath('message', 'El cuerpo es demasiado grande.');
});

it('answers 413 to a declared Content-Length over 10 MB', function () {
    RobotClient::post($this, ROBOT_TEST_PATH, [], headers: ['Content-Length' => (string) (10 * 1024 * 1024 + 1)])
        ->assertStatus(413);
});

it('answers 413 when the body inflates beyond the limit', function () {
    config(['sap.robot.max_decompressed_bytes' => 1000]);

    RobotClient::post($this, ROBOT_TEST_PATH, ['relleno' => str_repeat('a', 2000)], gzip: true)
        ->assertStatus(413);
});

it('answers 400 to a broken gzip or a body that is not a JSON object', function (string $body, bool $gzipHeader) {
    RobotClient::post($this, ROBOT_TEST_PATH, $body, headers: ['Content-Encoding' => $gzipHeader ? 'gzip' : null])
        ->assertStatus(400);
})->with([
    'not gzip' => ['{"conjunto":"CARTERA"}', true],
    'not JSON' => ['{"conjunto":', false],
    'a JSON list' => ['[1,2]', false],
    'a JSON string' => ['"hola"', false],
]);

it('answers 415 to an encoding other than gzip', function () {
    RobotClient::post($this, ROBOT_TEST_PATH, [], headers: ['Content-Encoding' => 'br'])->assertStatus(415);
});

it('limits the robot to the configured requests per minute per IP', function () {
    config(['sap.robot.requests_per_minute' => 2]);

    RobotClient::post($this, ROBOT_TEST_PATH)->assertOk();
    RobotClient::post($this, ROBOT_TEST_PATH)->assertOk();
    RobotClient::post($this, ROBOT_TEST_PATH)->assertStatus(429)->assertHeader('Retry-After');
});

it('forgets nonces older than ten minutes', function () {
    $this->freezeSecond();
    $store = app(NonceStore::class);

    $store->remember(RobotClient::KEY, str_repeat('a', 32));
    Carbon::setTestNow(now()->addMinutes(10)->addSecond());
    $store->remember(RobotClient::KEY, str_repeat('b', 32));

    expect($store->prune())->toBe(1)
        ->and(DB::table('robot_nonces')->pluck('nonce')->all())->toBe([str_repeat('b', 32)]);
});
