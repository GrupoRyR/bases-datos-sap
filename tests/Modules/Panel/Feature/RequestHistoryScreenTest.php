<?php

use App\Models\User;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\RequestScope;
use App\Modules\Sap\Contracts\Enums\RequestState;
use App\Modules\Sap\Contracts\RequestHistory;
use Carbon\CarbonImmutable;
use Tests\Modules\Panel\Support\FakeRequestHistory;

beforeEach(function () {
    $this->travelTo(CarbonImmutable::parse('2026-10-29 11:00', 'America/Bogota'));

    $this->history = function (array $items = [], ?int $total = null): FakeRequestHistory {
        $fake = new FakeRequestHistory($items, $total);
        $this->app->instance(RequestHistory::class, $fake);

        return $fake;
    };

    ($this->history)();

    $this->consulta = fn () => $this->actingAs(User::factory()->consulta()->create());
});

it('sends a guest to the sign-in page', function () {
    $this->get('/panel/solicitudes')->assertRedirect('/login');
});

it('forbids a user without a role', function () {
    $this->actingAs(User::factory()->create())->get('/panel/solicitudes')->assertForbidden();
});

it('shows the history to every role', function (string $role) {
    $this->actingAs(User::factory()->{$role}()->create())
        ->get(route('panel.solicitudes'))
        ->assertOk()
        ->assertViewIs('panel::solicitudes')
        ->assertSee('Historial de solicitudes')
        ->assertSee('Quién pidió datos frescos, cuándo, cuánto tardó y cómo terminó.');
})->with(['consulta', 'adminTi']);

it('shows each request with what it asked for, when and who asked', function () {
    ($this->history)([
        FakeRequestHistory::item(id: 119, scope: RequestScope::Customers, requesters: [
            FakeRequestHistory::requester(app: 'Toma de pedidos', email: 'luis@segurex.com', name: 'Luis Gómez'),
            FakeRequestHistory::requester(email: 'ana@segurex.com', name: 'Ana Ruiz', joinedAt: '2026-10-29 10:42'),
            FakeRequestHistory::requester(app: 'Gestor de cartera', email: 'sin.nombre@segurex.com', name: null, joinedAt: '2026-10-29 10:43'),
        ]),
        FakeRequestHistory::item(id: 118, company: Company::Sdc, dataset: Dataset::Cartera),
    ]);

    ($this->consulta)()->get('/panel/solicitudes')
        ->assertOk()
        ->assertSeeInOrder(['Solicitud 119', 'Segurex', 'Maestros', 'Clientes (con direcciones y contactos)', 'Pedida el 29 oct a las 10:40'])
        ->assertSeeInOrder(['Toma de pedidos', 'Luis Gómez', 'luis@segurex.com'])
        ->assertSeeInOrder(['Panel', 'Ana Ruiz', 'ana@segurex.com', 'Se unió el 29 oct a las 10:42'])
        ->assertSeeInOrder(['Gestor de cartera', 'sin.nombre@segurex.com', 'Se unió el 29 oct a las 10:43'])
        ->assertSeeInOrder(['Solicitud 118', 'Derivados', 'Cartera', 'Todo el conjunto']);
});

it('does not say the creator joined their own request', function () {
    ($this->history)([FakeRequestHistory::item()]);

    ($this->consulta)()->get('/panel/solicitudes')->assertDontSee('Se unió');
});

it('says how long a request took from the moment the robot took it', function (?string $finishedAt, string $text) {
    ($this->history)([FakeRequestHistory::item(takenAt: '2026-10-29 10:40', finishedAt: $finishedAt)]);

    ($this->consulta)()->get('/panel/solicitudes')->assertSee($text);
})->with([
    'minutes' => ['2026-10-29 10:44:59', 'Tardó 4 min'],
    'under a minute' => ['2026-10-29 10:40:45', 'Tardó menos de un minuto'],
    'hours' => ['2026-10-29 11:45', 'Tardó 1 h 5 min'],
]);

it('does not count the time a request waited in the queue', function () {
    ($this->history)([FakeRequestHistory::item(
        state: RequestState::Done,
        runFrom: '2026-10-29 10:35',
        takenAt: '2026-10-29 10:40',
        finishedAt: '2026-10-29 10:44',
        requestedAt: '2026-10-29 10:00',
    )]);

    ($this->consulta)()->get('/panel/solicitudes')
        ->assertSee('Tardó 4 min')
        ->assertDontSee('Tardó 44 min');
});

it('shows a dash when the run never started or has not finished', function (RequestState $state, ?string $takenAt, ?string $finishedAt) {
    ($this->history)([FakeRequestHistory::item(state: $state, takenAt: $takenAt, finishedAt: $finishedAt)]);

    ($this->consulta)()->get('/panel/solicitudes')->assertSee('Tardó —');
})->with([
    'pending' => [RequestState::Pending, null, null],
    'queued' => [RequestState::Queued, null, null],
    'closed without being taken' => [RequestState::Failed, null, '2026-10-29 10:44'],
    'still running' => [RequestState::Taken, '2026-10-29 10:40', null],
]);

it('shows the result of each state in words', function (RequestState $state, string $label, string $tone) {
    ($this->history)([FakeRequestHistory::item(state: $state, finishedAt: null)]);

    ($this->consulta)()->get('/panel/solicitudes')
        ->assertSee($label)
        ->assertSee("bg-{$tone}", false);
})->with([
    'done' => [RequestState::Done, 'Terminada', 'success-bg'],
    'failed' => [RequestState::Failed, 'Falló', 'danger-bg'],
    'expired' => [RequestState::Expired, 'Venció', 'warning-bg'],
    'taken' => [RequestState::Taken, 'En curso', 'info-bg'],
    'pending' => [RequestState::Pending, 'Pendiente', 'subtle'],
    'queued' => [RequestState::Queued, 'En cola', 'subtle'],
]);

it('explains why a request failed', function () {
    ($this->history)([FakeRequestHistory::item(state: RequestState::Failed, error: 'El lote 3 de clientes no llegó.')]);

    ($this->consulta)()->get('/panel/solicitudes')
        ->assertSee('Por qué falló')
        ->assertSee('El lote 3 de clientes no llegó.');
});

it('says when a queued request runs', function (?string $runFrom, string $text) {
    ($this->history)([FakeRequestHistory::item(state: RequestState::Queued, runFrom: $runFrom, finishedAt: null)]);

    ($this->consulta)()->get('/panel/solicitudes')->assertSee($text);
})->with([
    'today' => ['2026-10-29 12:45', 'Corre a las 12:45'],
    'tomorrow' => ['2026-10-30 00:15', 'Corre el 30 oct a las 00:15'],
    'behind a sister' => [null, 'Espera a que termine otra'],
]);

it('lists every company and dataset in the filters', function () {
    $response = ($this->consulta)()->get('/panel/solicitudes')->assertSee('Todas')->assertSee('Todos');

    foreach ([...Company::cases(), ...Dataset::cases()] as $case) {
        $response->assertSee('<option value="'.$case->value.'"', false);
    }
});

it('passes the filters and the page to the contract', function () {
    $fake = ($this->history)([FakeRequestHistory::item()], 60);

    ($this->consulta)()->get('/panel/solicitudes?empresa=SDC&conjunto=CARTERA&page=2')
        ->assertOk()
        ->assertSee('<option value="SDC" selected>', false)
        ->assertSee('<option value="CARTERA" selected>', false);

    expect($fake->calls)->toBe([['page' => 2, 'perPage' => 25, 'company' => Company::Sdc, 'dataset' => Dataset::Cartera]]);
});

it('ignores unknown filters and pages', function () {
    $fake = ($this->history)();

    ($this->consulta)()->get('/panel/solicitudes?empresa=XYZ&conjunto=COMPRAS&page=abc')->assertOk();

    expect($fake->calls)->toBe([['page' => 1, 'perPage' => 25, 'company' => null, 'dataset' => null]]);
});

it('links to older and newer pages keeping the filters', function () {
    ($this->history)([FakeRequestHistory::item()], 60);

    ($this->consulta)()->get('/panel/solicitudes?empresa=SGX&conjunto=MAESTROS&page=2')
        ->assertSee('Página 2 de 3')
        ->assertSee('Anteriores')
        ->assertSee(route('panel.solicitudes', ['empresa' => 'SGX', 'conjunto' => 'MAESTROS', 'page' => 3]))
        ->assertSee('Más recientes')
        ->assertSee(route('panel.solicitudes', ['empresa' => 'SGX', 'conjunto' => 'MAESTROS', 'page' => 1]));
});

it('offers no older page on the last one and no pages when one is enough', function () {
    ($this->history)([FakeRequestHistory::item()], 60);

    ($this->consulta)()->get('/panel/solicitudes?page=3')
        ->assertSee('Página 3 de 3')
        ->assertSee('Más recientes')
        ->assertDontSee('Anteriores');

    ($this->history)([FakeRequestHistory::item()]);

    ($this->consulta)()->get('/panel/solicitudes')
        ->assertDontSee('Página 1 de 1')
        ->assertDontSee('Más recientes');
});

it('sends a page past the end to the last page', function () {
    ($this->history)([], 30);

    ($this->consulta)()->get('/panel/solicitudes?conjunto=MAESTROS&page=9')
        ->assertRedirect(route('panel.solicitudes', ['conjunto' => 'MAESTROS', 'page' => 2]));
});

it('says when there are no requests yet', function () {
    ($this->consulta)()->get('/panel/solicitudes')
        ->assertOk()
        ->assertSee('Aún no hay solicitudes.');
});
