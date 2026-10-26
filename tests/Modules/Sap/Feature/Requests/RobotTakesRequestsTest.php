<?php

use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Contracts\Enums\RequestScope;
use App\Modules\Sap\Contracts\Enums\RequestState;
use App\Modules\Sap\Contracts\UpdateRequests;
use App\Modules\Sap\Models\UpdateRequest;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Tests\Modules\Sap\Support\RobotClient;
use Tests\TestCase;

/*
| The robot's side of update requests (docs/contrato-robot.md, section 7.3):
| it takes the ones whose time came, serves them in a run, and they end with
| the run or expire after 30 minutes taken.
*/

beforeEach(function () {
    RobotClient::configure();
    Carbon::setTestNow(Carbon::parse('2026-10-26 10:00:00', 'America/Bogota'));
});

function requestUpdate(?RequestScope $scope = RequestScope::Customers, Dataset $dataset = Dataset::Maestros, Company $company = Company::Sgx): int
{
    return app(UpdateRequests::class)->request($company, $dataset, $scope, 'ana@segurex.com', 'Ana Ruiz')->id;
}

function stateOf(int $id): RequestState
{
    return UpdateRequest::findOrFail($id)->estado;
}

/** @return array<string, mixed> */
function take(TestCase $test, int $max = 20): array
{
    return RobotClient::post($test, '/api/robot/v1/solicitudes/tomar', ['max' => $max])->assertOk()->json();
}

it('takes the requests whose time came, oldest first, and answers what to bring', function () {
    DB::connection('maestros')->table('clientes')->insert([
        ['empresa' => 'SGX', 'codigo' => 'C1', 'nombre' => 'Uno', 'activo' => true, 'actualizado_en_sap' => '2026-10-23 09:58:00', 'sincronizado_en' => now()],
        ['empresa' => 'SGX', 'codigo' => 'C2', 'nombre' => 'Dos', 'activo' => true, 'actualizado_en_sap' => '2026-10-20 08:00:00', 'sincronizado_en' => now()],
        ['empresa' => 'SDC', 'codigo' => 'C3', 'nombre' => 'Otra', 'activo' => true, 'actualizado_en_sap' => '2026-10-25 08:00:00', 'sincronizado_en' => now()],
    ]);
    $customers = requestUpdate();
    $cartera = requestUpdate(null, Dataset::Cartera);

    $taken = take($this)['solicitudes'];

    expect($taken)->toBe([
        [
            'id' => $customers, 'empresa' => 'SGX', 'conjunto' => 'MAESTROS', 'parte' => 'clientes',
            'desde' => ['clientes' => '2026-10-23T09:58:00-05:00'],
            'solicitada_en' => '2026-10-26T10:00:00-05:00',
        ],
        [
            'id' => $cartera, 'empresa' => 'SGX', 'conjunto' => 'CARTERA', 'parte' => null,
            'desde' => [],
            'solicitada_en' => '2026-10-26T10:00:00-05:00',
        ],
    ])->and(stateOf($customers))->toBe(RequestState::Taken)
        ->and(UpdateRequest::find($customers)->tomada_en->equalTo(now()))->toBeTrue();
});

it('asks for everything that changed in each part of a whole MAESTROS request, or all of it when MySQL is empty', function () {
    requestUpdate(null);

    expect(take($this)['solicitudes'][0]['desde'])->toBe(['clientes' => null, 'proveedores' => null, 'articulos' => null]);
});

it('answers an empty list when there is nothing to do', function () {
    expect(take($this))->toBe(['solicitudes' => []]);
});

it('takes no more than max, and queued requests only once their time came', function () {
    requestUpdate(RequestScope::Customers);
    requestUpdate(null, Dataset::Cartera);
    $queued = requestUpdate(RequestScope::Prices, company: Company::Sdc);
    DB::table('update_requests')->where('id', $queued)->update(['estado' => 'en_cola', 'correr_desde' => now()->addMinutes(2)]);

    expect(take($this, 1)['solicitudes'])->toHaveCount(1)
        ->and(take($this)['solicitudes'])->toHaveCount(1)
        ->and(stateOf($queued))->toBe(RequestState::Queued);

    $this->travel(2)->minutes();

    expect(take($this)['solicitudes'][0]['id'])->toBe($queued);
});

it('leaves a sister waiting while the robot serves another request of its company and dataset', function () {
    requestUpdate(RequestScope::Customers);
    $items = requestUpdate(RequestScope::Items);
    take($this, 1);

    // A second run of SGX MAESTROS could not start while the first is open.
    expect(take($this)['solicitudes'])->toBe([])
        ->and(stateOf($items))->toBe(RequestState::Pending);
});

it('validates max', function (mixed $max) {
    RobotClient::post($this, '/api/robot/v1/solicitudes/tomar', ['max' => $max])
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('max');
})->with([0, 101, '5']);

it('links the taken requests to the run that serves them and refuses others', function () {
    $taken = requestUpdate();
    $pending = requestUpdate(RequestScope::Items, company: Company::Sdc);
    take($this, 1);

    $run = RobotClient::openRun($this, ['solicitudes' => [$taken]]);

    expect(UpdateRequest::find($taken)->run_id)->toBe($run);

    // Already served by that run: another run cannot claim it.
    RobotClient::post($this, '/api/robot/v1/corridas', [
        'conjunto' => 'CARTERA', 'empresa' => 'SGX', 'tipo' => 'solicitud', 'partes' => ['cartera' => 'todo'],
        'solicitudes' => [$taken], 'fecha_corte' => '2026-10-26', 'extraida_en' => now()->toIso8601String(),
    ])->assertUnprocessable()->assertJsonValidationErrorFor('solicitudes');

    RobotClient::post($this, '/api/robot/v1/corridas', [
        'conjunto' => 'MAESTROS', 'empresa' => 'SDC', 'tipo' => 'solicitud', 'partes' => ['articulos' => 'cambios'],
        'solicitudes' => [$pending], 'fecha_corte' => null, 'extraida_en' => now()->toIso8601String(),
    ])->assertUnprocessable()->assertJsonValidationErrorFor('solicitudes');
});

it('refuses requests of another company or parts the run does not bring', function (array $run) {
    $taken = requestUpdate();
    take($this);

    RobotClient::post($this, '/api/robot/v1/corridas', array_merge([
        'conjunto' => 'MAESTROS', 'empresa' => 'SGX', 'tipo' => 'solicitud', 'partes' => ['clientes' => 'cambios', 'direcciones' => 'cambios', 'contactos' => 'cambios'],
        'solicitudes' => [$taken], 'fecha_corte' => null, 'extraida_en' => now()->toIso8601String(),
    ], $run))->assertUnprocessable()->assertJsonValidationErrorFor('solicitudes');
})->with([
    'another company' => [['empresa' => 'SDC']],
    'missing contacts' => [['partes' => ['clientes' => 'cambios', 'direcciones' => 'cambios']]],
]);

it('finishes the requests when their run closes and releases the queued sisters 3 minutes later', function () {
    $taken = requestUpdate();
    take($this);
    $queued = requestUpdate(RequestScope::Items);
    $run = RobotClient::openRun($this, ['solicitudes' => [$taken]]);
    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", RobotClient::batch(1, Part::Customers, [RobotClient::row(Part::Customers)]));

    $this->travel(5)->minutes();
    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['clientes' => 1, 'direcciones' => 0, 'contactos' => 0]])->assertOk();

    $done = UpdateRequest::find($taken);
    $released = UpdateRequest::find($queued);

    expect($done->estado)->toBe(RequestState::Done)
        ->and($done->terminada_en->equalTo(now()))->toBeTrue()
        ->and($released->estado)->toBe(RequestState::Queued)
        ->and($released->correr_desde->equalTo(now()->addMinutes(3)))->toBeTrue();
});

it('fails the requests with the run error and releases the sisters right away', function () {
    $taken = requestUpdate();
    take($this);
    $queued = requestUpdate();
    $run = RobotClient::openRun($this, ['solicitudes' => [$taken]]);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/fallar", ['error' => 'VPN no conectó en 3 intentos'])->assertOk();

    expect(stateOf($taken))->toBe(RequestState::Failed)
        ->and(UpdateRequest::find($taken)->error)->toBe('VPN no conectó en 3 intentos')
        ->and(stateOf($queued))->toBe(RequestState::Pending)
        ->and(UpdateRequest::find($queued)->correr_desde->equalTo(now()))->toBeTrue();
});

it('expires the requests of a run that expired', function () {
    $taken = requestUpdate();
    take($this);
    RobotClient::openRun($this, ['solicitudes' => [$taken]]);

    $this->travel(31)->minutes();
    $this->artisan('sap:vencer')->assertSuccessful();

    expect(stateOf($taken))->toBe(RequestState::Expired);
});

it('expires a request taken 30 minutes ago without finishing, and keeps it expired if its run closes later', function () {
    $taken = requestUpdate();
    take($this);
    $this->travel(20)->minutes();
    $run = RobotClient::openRun($this, ['solicitudes' => [$taken]]);
    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", RobotClient::batch(1, Part::Customers, [RobotClient::row(Part::Customers, ['codigo' => 'C1'])]));

    $this->travel(11)->minutes();
    $this->artisan('sap:vencer')->assertSuccessful();

    expect(stateOf($taken))->toBe(RequestState::Expired);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['clientes' => 1, 'direcciones' => 0, 'contactos' => 0]])->assertOk();

    // The data is applied anyway; the request stays expired as the signal it took too long.
    expect(stateOf($taken))->toBe(RequestState::Expired)
        ->and(DB::connection('maestros')->table('clientes')->where('codigo', 'C1')->exists())->toBeTrue();
});
