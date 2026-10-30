<?php

use App\Models\User;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\RequestScope;
use App\Modules\Sap\Contracts\Enums\RequestState;
use App\Modules\Sap\Contracts\UpdateRequests;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;
use Tests\Modules\Panel\Support\FakeUpdateRequests;

beforeEach(function () {
    $this->travelTo(CarbonImmutable::parse('2026-10-29 10:40', 'America/Bogota'));

    $this->updates = function (...$arguments): FakeUpdateRequests {
        $fake = new FakeUpdateRequests(...$arguments);
        $this->app->instance(UpdateRequests::class, $fake);

        return $fake;
    };

    $this->fake = ($this->updates)();

    $this->admin = User::factory()->adminTi()->create(['name' => 'Jhon Pérez', 'email' => 'ti@segurex.com']);
});

it('sends a guest to the sign-in page', function () {
    $this->get('/panel/actualizar')->assertRedirect('/login');
    $this->post('/panel/actualizar')->assertRedirect('/login');
});

it('forbids consulta and users without a role', function (?string $role) {
    $user = $role === null ? User::factory()->create() : User::factory()->{$role}()->create();

    $this->actingAs($user)->get('/panel/actualizar')->assertForbidden();
    $this->actingAs($user)->post('/panel/actualizar', ['empresa' => 'SGX', 'datos' => 'CARTERA'])->assertForbidden();

    expect($this->fake->calls)->toBe([]);
})->with(['consulta' => 'consulta', 'no role' => null]);

it('shows the form with every company and every dataset and scope', function () {
    $response = $this->actingAs($this->admin)
        ->get(route('panel.actualizar'))
        ->assertOk()
        ->assertViewIs('panel::actualizar')
        ->assertSee('Actualizar datos')
        ->assertSee('Si ya hay una igual esperando, te unes a ella; si se actualizó hace menos de 3 minutos o cae en una franja de los otros robots, queda en cola. Nunca se rechaza.')
        ->assertSee(route('panel.solicitudes'))
        ->assertSee('Maestros: todo')
        ->assertSee('Maestros: clientes (con direcciones y contactos)')
        ->assertSee('Cartera: todo');

    $html = $response->getContent();
    $expected = array_sum(array_map(fn (Dataset $dataset): int => 1 + count(RequestScope::forDataset($dataset)), Dataset::cases()));

    expect(substr_count($html, 'name="empresa"'))->toBe(count(Company::cases()))
        ->and(substr_count($html, 'name="datos"'))->toBe($expected);

    foreach (Company::cases() as $company) {
        $response->assertSee('value="'.$company->value.'"', false);
    }

    foreach (Dataset::cases() as $dataset) {
        $response->assertSee('value="'.$dataset->value.'"', false);

        foreach (RequestScope::forDataset($dataset) as $scope) {
            $response->assertSee('value="'.$dataset->value.':'.$scope->value.'"', false);
        }
    }
});

it('asks Sap for the chosen company, dataset and scope in the name of the user', function (string $value, Dataset $dataset, ?RequestScope $scope) {
    $this->actingAs($this->admin)
        ->post('/panel/actualizar', ['empresa' => 'SDC', 'datos' => $value])
        ->assertRedirect(route('panel.actualizar'))
        ->assertSessionHasNoErrors();

    expect($this->fake->calls)->toBe([[
        'company' => Company::Sdc,
        'dataset' => $dataset,
        'scope' => $scope,
        'email' => 'ti@segurex.com',
        'name' => 'Jhon Pérez',
    ]]);
})->with([
    'whole maestros' => ['MAESTROS', Dataset::Maestros, null],
    'customers' => ['MAESTROS:clientes', Dataset::Maestros, RequestScope::Customers],
    'catalogs' => ['MAESTROS:catalogos', Dataset::Maestros, RequestScope::Catalogs],
    'cartera' => ['CARTERA', Dataset::Cartera, null],
]);

it('says what happened to the request', function (array $answer, string $message) {
    ($this->updates)(...$answer);

    $this->actingAs($this->admin)
        ->followingRedirects()
        ->post('/panel/actualizar', ['empresa' => 'SGX', 'datos' => 'MAESTROS:precios'])
        ->assertOk()
        ->assertSee($message);
})->with([
    'joined' => [['created' => false], 'Ya había una solicitud igual esperando; te uniste a la solicitud 118.'],
    'joined a queued one' => [['state' => RequestState::Queued, 'runFrom' => '2026-10-29 12:45', 'created' => false], 'Ya había una solicitud igual esperando; te uniste a la solicitud 118, que se actualizará a las 12:45.'],
    'pending' => [[], 'Pedimos los datos a SAP (solicitud 118). Suele tardar unos minutos.'],
    'queued until a time' => [['state' => RequestState::Queued, 'runFrom' => '2026-10-29 12:45'], 'Se actualizará a las 12:45 (solicitud 118).'],
    'queued until tomorrow' => [['state' => RequestState::Queued, 'runFrom' => '2026-10-30 00:15'], 'Se actualizará el 30 oct a las 00:15 (solicitud 118).'],
    'queued behind a sister' => [['state' => RequestState::Queued, 'runFrom' => null], 'Hay otra actualización en curso; esta sigue después (solicitud 118).'],
]);

it('rejects what is not an option without asking Sap', function (array $input, string $field) {
    $this->actingAs($this->admin)
        ->from('/panel/actualizar')
        ->post('/panel/actualizar', $input)
        ->assertRedirect('/panel/actualizar')
        ->assertSessionHasErrors($field);

    expect($this->fake->calls)->toBe([])
        ->and(DB::table('audit_logs')->count())->toBe(0);
})->with([
    'scope of cartera' => [['empresa' => 'SGX', 'datos' => 'CARTERA:clientes'], 'datos'],
    'unknown scope' => [['empresa' => 'SGX', 'datos' => 'MAESTROS:pedidos'], 'datos'],
    'unknown dataset' => [['empresa' => 'SGX', 'datos' => 'COMPRAS'], 'datos'],
    'missing data' => [['empresa' => 'SGX'], 'datos'],
    'unknown company' => [['empresa' => 'XYZ', 'datos' => 'CARTERA'], 'empresa'],
    'missing company' => [['datos' => 'CARTERA'], 'empresa'],
]);

it('shows the validation message next to the group and keeps the choice', function () {
    $html = $this->actingAs($this->admin)
        ->followingRedirects()
        ->from('/panel/actualizar')
        ->post('/panel/actualizar', ['empresa' => 'SDC', 'datos' => 'CARTERA:clientes'])
        ->assertSee('Elige qué actualizar de la lista.')
        ->assertSee('aria-describedby="error-datos"', false)
        ->assertDontSee('aria-describedby="error-empresa"', false)
        ->getContent();

    expect($html)->toMatch('/value="SDC"[^>]*\schecked>/')
        ->not->toMatch('/value="SGX"[^>]*\schecked>/');
});

it('audits the request with its codes and whether the user joined', function (bool $created) {
    ($this->updates)(state: RequestState::Pending, created: $created);

    $this->actingAs($this->admin)->post('/panel/actualizar', ['empresa' => 'SGX', 'datos' => 'MAESTROS:clientes']);

    $row = DB::table('audit_logs')->sole();

    expect($row->action)->toBe('panel.request.placed')
        ->and($row->subject_type)->toBe('request')
        ->and($row->subject_id)->toBe('118')
        ->and((int) $row->user_id)->toBe($this->admin->id)
        ->and(json_decode((string) $row->context, true))->toEqual([
            'empresa' => 'SGX',
            'conjunto' => 'MAESTROS',
            'parte' => 'clientes',
            'joined' => ! $created,
        ]);
})->with(['created' => true, 'joined' => false]);
