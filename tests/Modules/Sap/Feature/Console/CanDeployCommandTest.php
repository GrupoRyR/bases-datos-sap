<?php

use App\Modules\Sap\Models\Run;
use App\Modules\Sap\Models\UpdateRequest;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;

/*
| sap:puede-desplegar: the deploy dispatcher asks it before each deploy,
| because maintenance mode in the middle of a run kills it (the robot
| retries a 5xx only 3 times within 14 seconds). It prints `ok` and exits 0,
| or prints one reason and exits 1. Times are in Bogota.
*/

const DEPLOY_SLOT_MESSAGE = 'Ahora no: estás a 15 minutos o menos de una franja bloqueada.';
const DEPLOY_NIGHTLY_MESSAGE = 'Ahora no: estás en la ventana de la corrida nocturna (01:45-02:15).';
const DEPLOY_RUN_MESSAGE = 'Ahora no: hay una corrida del robot abierta.';
const DEPLOY_REQUEST_MESSAGE = 'Ahora no: hay una solicitud tomada por el robot que no ha vencido.';

function deployAt(string $time, string $day = '2026-10-27'): void
{
    test()->travelTo(CarbonImmutable::parse("{$day} {$time}", 'America/Bogota'));
}

/** @param  array<string, mixed>  $attributes */
function deployRun(array $attributes = []): Run
{
    return Run::forceCreate(array_merge([
        'conjunto' => 'MAESTROS', 'empresa' => 'SGX', 'tipo' => 'solicitud', 'partes' => ['clientes' => 'cambios'],
        'solicitudes' => [], 'extraida_en' => now(), 'estado' => 'abierta', 'abierta_lock' => 'MAESTROS:SGX',
        'abierta_hasta' => now()->addMinutes(Run::IDLE_MINUTES), 'robot_key' => 'r2026a',
    ], $attributes));
}

function deployRequest(string $state, ?CarbonImmutable $takenAt): int
{
    return DB::table('update_requests')->insertGetId([
        'empresa' => 'SGX', 'conjunto' => 'MAESTROS', 'estado' => $state, 'correr_desde' => $takenAt,
        'tomada_en' => $takenAt, 'created_at' => now(), 'updated_at' => now(),
    ]);
}

beforeEach(function () {
    config()->set('sap.requests.blocked_slots', '00:00,05:00,06:00,12:00,12:30');
    config()->set('sap.requests.slot_margin_minutes', 15);
    config()->set('sap.deploy.nightly_window', '01:45-02:15');

    deployAt('10:00');
});

it('says ok when nothing is running and no slot or window is near', function () {
    $this->artisan('sap:puede-desplegar')
        ->expectsOutput('ok')
        ->doesntExpectOutputToContain('Ahora no')
        ->assertExitCode(0);
});

it('refuses near a blocked slot', function (string $time) {
    deployAt($time);

    $this->artisan('sap:puede-desplegar')->expectsOutput(DEPLOY_SLOT_MESSAGE)->assertExitCode(1);
})->with([
    'before the slot' => ['11:50'],
    'on the slot' => ['12:00'],
    'between touching slots' => ['12:20'],
    'after midnight' => ['00:05'],
    'before midnight' => ['23:50'],
]);

it('uses the same margin edges as update requests', function (string $time, int $exitCode) {
    // BlockedSlots: from margin minutes before the slot (inclusive) until margin minutes after it (exclusive).
    config()->set('sap.requests.blocked_slots', '08:00');
    deployAt($time);

    $this->artisan('sap:puede-desplegar')
        ->expectsOutput($exitCode === 0 ? 'ok' : DEPLOY_SLOT_MESSAGE)
        ->assertExitCode($exitCode);
})->with([
    'one minute beyond the margin before' => ['07:44', 0],
    'one second beyond the margin before' => ['07:44:59', 0],
    'exactly the margin before' => ['07:45', 1],
    'one minute inside the margin after' => ['08:14', 1],
    'one second inside the margin after' => ['08:14:59', 1],
    'exactly the margin after' => ['08:15', 0],
    'one minute beyond the margin after' => ['08:16', 0],
]);

it('honours configured blocked slots and margin', function () {
    config()->set('sap.requests.blocked_slots', '10:30');
    config()->set('sap.requests.slot_margin_minutes', 30);

    $this->artisan('sap:puede-desplegar')
        ->expectsOutput('Ahora no: estás a 30 minutos o menos de una franja bloqueada.')
        ->assertExitCode(1);

    config()->set('sap.requests.slot_margin_minutes', 29);

    $this->artisan('sap:puede-desplegar')->expectsOutput('ok')->assertExitCode(0);
});

it('refuses inside the nightly run window, start included and end excluded', function (string $time, int $exitCode) {
    deployAt($time);

    $this->artisan('sap:puede-desplegar')
        ->expectsOutput($exitCode === 0 ? 'ok' : DEPLOY_NIGHTLY_MESSAGE)
        ->assertExitCode($exitCode);
})->with([
    'just before the start' => ['01:44:59', 0],
    'the start' => ['01:45', 1],
    'the nightly run' => ['02:00', 1],
    'just before the end' => ['02:14:59', 1],
    'the end' => ['02:15', 0],
]);

it('handles a nightly window that crosses midnight', function (string $time, int $exitCode) {
    config()->set('sap.requests.blocked_slots', '');
    config()->set('sap.deploy.nightly_window', '23:30-00:30');
    deployAt($time);

    $this->artisan('sap:puede-desplegar')
        ->expectsOutput($exitCode === 0 ? 'ok' : 'Ahora no: estás en la ventana de la corrida nocturna (23:30-00:30).')
        ->assertExitCode($exitCode);
})->with([
    'before the start' => ['23:29', 0],
    'the start' => ['23:30', 1],
    'midnight' => ['00:00', 1],
    'just before the end' => ['00:29', 1],
    'the end' => ['00:30', 0],
    'midday' => ['12:00', 0],
]);

it('refuses when the nightly window is not valid', function (string $window) {
    config()->set('sap.deploy.nightly_window', $window);

    $this->artisan('sap:puede-desplegar')
        ->expectsOutput("Ahora no: la ventana nocturna configurada no es válida ({$window}).")
        ->assertExitCode(1);
})->with([
    'not two times' => ['1:45 a 2:15'],
    // An empty window would switch the guard off without a word.
    'start equal to end' => ['02:00-02:00'],
]);

it('reports a blocked slot before the nightly window', function () {
    config()->set('sap.requests.blocked_slots', '02:00');
    deployAt('02:00');

    $this->artisan('sap:puede-desplegar')->expectsOutput(DEPLOY_SLOT_MESSAGE)->assertExitCode(1);
});

it('refuses with an open run', function () {
    deployRun();

    $this->artisan('sap:puede-desplegar')->expectsOutput(DEPLOY_RUN_MESSAGE)->assertExitCode(1);
});

it('ignores finished runs and an open run already past its idle window', function () {
    deployRun(['estado' => 'cerrada', 'abierta_lock' => null]);
    deployRun(['conjunto' => 'CARTERA', 'abierta_lock' => 'CARTERA:SGX', 'abierta_hasta' => now()->subMinute()]);

    $this->artisan('sap:puede-desplegar')->expectsOutput('ok')->assertExitCode(0);
});

it('refuses with a taken request that has not expired', function () {
    deployRequest('tomada', CarbonImmutable::now()->subMinutes(29));

    $this->artisan('sap:puede-desplegar')->expectsOutput(DEPLOY_REQUEST_MESSAGE)->assertExitCode(1);
});

it('says ok with a taken request already past its expiry and with waiting requests', function () {
    deployRequest('tomada', CarbonImmutable::now()->subMinutes(30));
    deployRequest('pendiente', null);
    deployRequest('en_cola', null);

    $this->artisan('sap:puede-desplegar')->expectsOutput('ok')->assertExitCode(0);
});

it('reports an open run before a taken request', function () {
    deployRun();
    deployRequest('tomada', CarbonImmutable::now());

    $this->artisan('sap:puede-desplegar')->expectsOutput(DEPLOY_RUN_MESSAGE)->assertExitCode(1);
});

it('writes nothing, not even to expire what is stale', function () {
    $idle = deployRun(['abierta_hasta' => now()->subMinute()]);
    $stale = deployRequest('tomada', CarbonImmutable::now()->subMinutes(45));
    $before = [DB::table('robot_runs')->count(), DB::table('update_requests')->count()];

    $this->artisan('sap:puede-desplegar')->assertExitCode(0);

    expect([DB::table('robot_runs')->count(), DB::table('update_requests')->count()])->toBe($before)
        ->and($idle->fresh()->estado->value)->toBe('abierta')
        ->and(UpdateRequest::find($stale)->estado->value)->toBe('tomada');
});
