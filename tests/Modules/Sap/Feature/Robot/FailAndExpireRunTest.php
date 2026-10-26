<?php

use App\Modules\Sap\Domain\Runs\RunState;
use App\Modules\Sap\Models\Run;
use Illuminate\Support\Facades\DB;
use Tests\Modules\Sap\Support\RobotClient;
use Tests\TestCase;

/*
| Failing a run (docs/contrato-robot.md, section 4.4) and expiring runs
| that got no batch for 30 minutes (section 4.1).
*/

beforeEach(function () {
    RobotClient::configure();
    $this->freezeSecond();
});

/** Opens a MAESTROS run of SGX through the API and gives it one stored batch. */
function openRunWithBatch(TestCase $test): Run
{
    $id = RobotClient::post($test, '/api/robot/v1/corridas', [
        'conjunto' => 'MAESTROS', 'empresa' => 'SGX', 'tipo' => 'solicitud', 'partes' => ['vendedores' => 'todo'],
        'solicitudes' => [], 'fecha_corte' => null, 'extraida_en' => '2026-10-23T10:41:30-05:00',
    ])->assertCreated()->json('run_id');

    DB::table('robot_batches')->insert([
        'run_id' => $id, 'batch' => 1, 'parte' => 'vendedores', 'sha256' => str_repeat('a', 64),
        'rows_count' => 1, 'rows' => '[[7,"Ana Ruiz",null,null,true]]', 'created_at' => now(),
    ]);
    DB::table('robot_batch_keys')->insert(['run_id' => $id, 'parte' => 'vendedores', 'key_hash' => str_repeat('b', 64)]);

    return Run::findOrFail($id);
}

it('fails a run with the robot message and discards its batches', function () {
    $run = openRunWithBatch($this);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run->id}/fallar", ['error' => 'VPN no conectó en 3 intentos'])
        ->assertOk()
        ->assertExactJson(['run_id' => $run->id, 'estado' => 'fallida']);

    $run->refresh();

    expect($run->estado)->toBe(RunState::Failed)
        ->and($run->error)->toBe('VPN no conectó en 3 intentos')
        ->and($run->terminada_en->equalTo(now()))->toBeTrue()
        ->and(DB::table('robot_batches')->count())->toBe(0)
        ->and(DB::table('robot_batch_keys')->count())->toBe(0);
});

it('lets a new run start once the open one failed', function () {
    $run = openRunWithBatch($this);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run->id}/fallar", ['error' => 'Falla de red']);

    RobotClient::post($this, '/api/robot/v1/corridas', [
        'conjunto' => 'MAESTROS', 'empresa' => 'SGX', 'tipo' => 'solicitud', 'partes' => ['vendedores' => 'todo'],
        'solicitudes' => [], 'fecha_corte' => null, 'extraida_en' => '2026-10-23T10:50:00-05:00',
    ])->assertCreated();
});

it('requires a short error message', function (array $body) {
    $run = openRunWithBatch($this);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run->id}/fallar", $body)
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('error');

    expect($run->refresh()->estado)->toBe(RunState::Open);
})->with([
    'missing' => [[]],
    'empty' => [['error' => '  ']],
    'over 1,000 characters' => [['error' => str_repeat('x', 1001)]],
]);

it('answers 409 with the state to a run that is no longer open', function () {
    $run = openRunWithBatch($this);
    RobotClient::post($this, "/api/robot/v1/corridas/{$run->id}/fallar", ['error' => 'Primera falla']);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run->id}/fallar", ['error' => 'Segunda falla'])
        ->assertConflict()
        ->assertJsonPath('estado', 'fallida');

    expect($run->refresh()->error)->toBe('Primera falla');
});

it('answers 404 to an unknown run', function () {
    RobotClient::post($this, '/api/robot/v1/corridas/999/fallar', ['error' => 'x'])
        ->assertNotFound()
        ->assertExactJson(['message' => 'La corrida no existe.']);
});

it('expires runs that got no batch for 30 minutes and keeps the others open', function () {
    $idle = openRunWithBatch($this);

    $this->travel(20)->minutes();
    $fresh = Run::findOrFail(RobotClient::post($this, '/api/robot/v1/corridas', [
        'conjunto' => 'CARTERA', 'empresa' => 'SGX', 'tipo' => 'solicitud', 'partes' => ['cartera' => 'todo'],
        'solicitudes' => [], 'fecha_corte' => '2026-10-23', 'extraida_en' => '2026-10-23T11:00:00-05:00',
    ])->json('run_id'));

    $this->travelTo(now()->addMinutes(10)->addSecond());
    $this->artisan('sap:vencer')->assertSuccessful();

    expect($idle->refresh()->estado)->toBe(RunState::Expired)
        ->and($idle->error)->toBe('Pasaron 30 minutos sin recibir lotes.')
        ->and($fresh->refresh()->estado)->toBe(RunState::Open)
        ->and(DB::table('robot_batches')->where('run_id', $idle->id)->count())->toBe(0);
});

it('answers 409 to a run that expired while idle', function () {
    $run = openRunWithBatch($this);

    $this->travel(31)->minutes();

    RobotClient::post($this, "/api/robot/v1/corridas/{$run->id}/fallar", ['error' => 'Tarde'])
        ->assertConflict()
        ->assertJsonPath('estado', 'vencida');
});
