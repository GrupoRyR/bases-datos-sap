<?php

use App\Models\User;
use App\Modules\Sap\Contracts\DatasetStatuses;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Stability;
use App\Support\Navigation\NavItem;
use App\Support\Navigation\NavRegistry;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\Route;
use Tests\Modules\Panel\Support\FakeDatasetStatuses;
use Tests\Modules\Panel\Support\FakeStability;

beforeEach(function () {
    $this->travelTo(CarbonImmutable::parse('2026-10-29 10:00', 'America/Bogota'));

    $this->statuses = function (array $statuses): void {
        $this->app->instance(DatasetStatuses::class, new FakeDatasetStatuses($statuses));
    };

    ($this->statuses)([]);
    $this->app->instance(Stability::class, new FakeStability);
});

it('sends a guest to the sign-in page', function () {
    $this->get('/panel')->assertRedirect('/login');
});

it('forbids a user without a role', function () {
    $this->actingAs(User::factory()->create())->get('/panel')->assertForbidden();
});

it('shows the status screen to every role', function (string $role) {
    $this->actingAs(User::factory()->{$role}()->create())
        ->get(route('panel.estado'))
        ->assertOk()
        ->assertViewIs('panel::estado')
        ->assertSee('Estado de los datos')
        ->assertSee('Lo que trajo el robot de SAP por empresa y conjunto.');
})->with(['consulta', 'adminTi']);

it('shows the stability counter, the strip and the problems of the unstable days', function () {
    $this->app->instance(Stability::class, new FakeStability(9, [
        9 => ['La corrida nocturna de SDC MAESTROS falló.'],
        12 => ['Una solicitud tardó más de 10 minutos.'],
    ]));

    $response = $this->actingAs(User::factory()->consulta()->create())->get('/panel')->assertOk();

    $response->assertSee('Estable: 9 de 14 días')
        ->assertSee('<time datetime="2026-10-29">29 oct</time>', false)
        ->assertSee('<time datetime="2026-10-16">16 oct</time>', false)
        ->assertSee('Con fallas')
        ->assertSeeInOrder(['La corrida nocturna de SDC MAESTROS falló.', 'Una solicitud tardó más de 10 minutos.'])
        ->assertSee('Nadie corrigió datos a mano: lo revisa TI.');
});

it('marks today as in progress until it is stable', function () {
    $this->app->instance(Stability::class, new FakeStability(13, todayInProgress: true));

    $this->actingAs(User::factory()->consulta()->create())
        ->get('/panel')
        ->assertSee('En curso')
        ->assertDontSee('Con fallas');
});

it('shows each company and dataset with its rows, update time and last run', function () {
    ($this->statuses)([
        FakeDatasetStatuses::status(
            lastAppliedAt: CarbonImmutable::parse('2026-10-29 02:15', 'America/Bogota'),
            rows: ['clientes' => 1234567, 'grupos_articulos' => 42, 'condiciones_pago' => 0],
            lastRun: FakeDatasetStatuses::run(),
        ),
        FakeDatasetStatuses::status(company: Company::Sdc, dataset: Dataset::Cartera, rows: ['cartera' => 3500]),
    ]);

    $this->actingAs(User::factory()->consulta()->create())
        ->get('/panel')
        ->assertOk()
        ->assertSeeInOrder(['Segurex', 'Maestros', 'Derivados', 'Cartera'])
        ->assertSee('Actualizado el 29 oct a las 02:15')
        ->assertSeeInOrder(['Clientes', '1.234.567', 'Grupos de artículos', '42', 'Condiciones de pago', '0'])
        ->assertSee('3.500')
        ->assertSee('Nocturna')
        ->assertSee('Terminó bien')
        ->assertDontSee('Por qué falló');
});

it('explains why a run failed or expired', function (string $state, string $label) {
    ($this->statuses)([
        FakeDatasetStatuses::status(lastRun: FakeDatasetStatuses::run(
            state: $state,
            type: 'solicitud',
            error: 'El lote 3 de clientes no llegó.',
        )),
    ]);

    $this->actingAs(User::factory()->consulta()->create())
        ->get('/panel')
        ->assertSee('Por solicitud')
        ->assertSee($label)
        ->assertSee('Por qué falló')
        ->assertSee('El lote 3 de clientes no llegó.');
})->with([
    'failed' => ['fallida', 'Falló'],
    'expired' => ['vencida', 'Venció'],
]);

it('shows a run in progress without an end time', function () {
    ($this->statuses)([
        FakeDatasetStatuses::status(lastRun: FakeDatasetStatuses::run(state: 'abierta', finishedAt: null)),
    ]);

    $this->actingAs(User::factory()->consulta()->create())
        ->get('/panel')
        ->assertSee('En curso')
        ->assertSee('Empezó el 29 oct a las 02:00')
        ->assertDontSee('Terminó el');
});

it('says when a dataset has no data and no runs yet', function () {
    ($this->statuses)([FakeDatasetStatuses::status(rows: ['clientes' => 0])]);

    $this->actingAs(User::factory()->consulta()->create())
        ->get('/panel')
        ->assertSee('Sin datos aún')
        ->assertSee('Aún no hay corridas.');
});

it('lists the panel screens in the navigation, hiding the admin ones from consulta', function () {
    // T5 and T7 add these routes; until then a stand-in proves the permission.
    Route::get('panel/apps-de-prueba', fn () => 'ok')->name('panel.apps');
    Route::get('panel/actualizar-de-prueba', fn () => 'ok')->name('panel.actualizar');
    Route::getRoutes()->refreshNameLookups();

    $labels = fn (User $user): array => array_map(
        fn (NavItem $item): string => $item->label,
        app(NavRegistry::class)->visibleTo($user),
    );

    expect($labels(User::factory()->adminTi()->create()))->toContain('Estado', 'Actualizar datos', 'Apps conectadas')
        ->and($labels(User::factory()->consulta()->create()))->toContain('Estado')
        ->not->toContain('Actualizar datos')
        ->not->toContain('Apps conectadas');

    $this->actingAs(User::factory()->consulta()->create())
        ->get('/panel')
        ->assertSee('Estado')
        ->assertDontSee('Apps conectadas');
});
