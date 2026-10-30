<?php

use App\Models\User;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Contracts\MasterLookup;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;
use Tests\Modules\Panel\Support\FakeMasterLookup;

beforeEach(function () {
    $this->travelTo(CarbonImmutable::parse('2026-10-29 11:00', 'America/Bogota'));

    $this->lookup = function (array $records = []): FakeMasterLookup {
        $fake = new FakeMasterLookup($records);
        $this->app->instance(MasterLookup::class, $fake);

        return $fake;
    };

    $this->fake = ($this->lookup)();

    $this->admin = fn () => $this->actingAs(User::factory()->adminTi()->create());
});

it('sends a guest to the sign-in page', function () {
    $this->get('/panel/consulta')->assertRedirect('/login');
    $this->post('/panel/consulta', ['parte' => 'clientes', 'termino' => 'andina'])->assertRedirect('/login');

    expect($this->fake->calls)->toBe([]);
});

it('forbids consulta and users without a role (Ley 1581)', function (?string $role) {
    $user = $role === null ? User::factory()->create() : User::factory()->{$role}()->create();

    $this->actingAs($user)->get('/panel/consulta')->assertForbidden();
    $this->actingAs($user)->post('/panel/consulta', ['parte' => 'clientes', 'termino' => 'andina'])->assertForbidden();

    expect($this->fake->calls)->toBe([]);
})->with(['consulta' => 'consulta', 'no role' => null]);

it('shows the form with the searchable parts and the companies to TI', function () {
    $response = ($this->admin)()
        ->get(route('panel.consulta'))
        ->assertOk()
        ->assertViewIs('panel::consulta')
        ->assertSee('Consulta')
        ->assertSee('Código, nombre o NIT')
        ->assertSee('Las dos')
        ->assertSee('Buscar')
        ->assertSee('action="'.route('panel.consulta.buscar').'"', false)
        ->assertSee('method="POST"', false);

    $html = $response->getContent();

    expect(substr_count($html, 'name="parte"'))->toBe(3)
        ->and(substr_count($html, 'name="empresa"'))->toBe(1 + count(Company::cases()));

    $response->assertSeeInOrder(['Clientes', 'Proveedores', 'Artículos']);

    foreach (Company::cases() as $company) {
        $response->assertSee('value="'.$company->value.'"', false);
    }

    expect($this->fake->calls)->toBe([]);
});

it('asks the contract for the chosen part, term and company, up to the maximum', function (array $input, Part $part, ?Company $company) {
    ($this->admin)()
        ->post('/panel/consulta', [...$input, 'termino' => '  800123  '])
        ->assertOk()
        ->assertViewIs('panel::consulta');

    expect($this->fake->calls)->toBe([[
        'part' => $part,
        'term' => '800123',
        'company' => $company,
        'limit' => MasterLookup::MAX_RESULTS,
    ]]);
})->with([
    'customers of both' => [['parte' => 'clientes', 'empresa' => ''], Part::Customers, null],
    'customers, no company sent' => [['parte' => 'clientes'], Part::Customers, null],
    'suppliers of SGX' => [['parte' => 'proveedores', 'empresa' => 'SGX'], Part::Suppliers, Company::Sgx],
    'items of SDC' => [['parte' => 'articulos', 'empresa' => 'SDC'], Part::Items, Company::Sdc],
]);

it('shows each record with its code, name, NIT, company, state and dates', function () {
    ($this->lookup)([
        FakeMasterLookup::record(),
        FakeMasterLookup::record(company: Company::Sdc, code: 'C900555', name: 'Andina Trading', taxId: null, active: false, updatedInSap: null, syncedAt: '2026-10-28 02:20'),
    ]);

    ($this->admin)()
        ->post('/panel/consulta', ['parte' => 'clientes', 'termino' => 'andina'])
        ->assertOk()
        ->assertSee('2 resultados')
        ->assertSeeInOrder([
            'Ferretería Andina SAS', 'Activo', 'C800123456 · NIT 800123456-1 · Segurex',
            'Cambió en SAP el 23 oct a las 09:15', 'Llegó aquí el 29 oct a las 02:15',
            'Andina Trading', 'Inactivo', 'C900555 · Derivados',
            'SAP no da la fecha de cambio', 'Llegó aquí el 28 oct a las 02:20',
        ])
        ->assertSee('<time datetime="2026-10-23T09:15:00-05:00">', false)
        ->assertDontSee('Se muestran los primeros');
});

it('says 1 resultado and keeps the choices in the form', function () {
    ($this->lookup)([FakeMasterLookup::record()]);

    $html = ($this->admin)()
        ->post('/panel/consulta', ['parte' => 'proveedores', 'empresa' => 'SDC', 'termino' => 'andina'])
        ->assertSee('1 resultado')
        ->assertDontSee('1 resultados')
        ->assertSee('value="andina"', false)
        ->getContent();

    expect($html)->toMatch('/value="proveedores"[^>]*\schecked>/')
        ->toMatch('/value="SDC"[^>]*\schecked>/')
        ->not->toMatch('/value="clientes"[^>]*\schecked>/');
});

it('hides the NIT of items', function () {
    ($this->lookup)([FakeMasterLookup::record(part: Part::Items, code: 'A-1020', name: 'Guante de nitrilo', taxId: null)]);

    ($this->admin)()
        ->post('/panel/consulta', ['parte' => 'articulos', 'termino' => 'guante'])
        ->assertSee('Guante de nitrilo')
        ->assertSee('A-1020')
        ->assertDontSee('NIT ');
});

it('says only the first ones are shown when the results reach the maximum', function () {
    ($this->lookup)(array_map(
        fn (int $index) => FakeMasterLookup::record(code: "C{$index}", name: "Cliente {$index}"),
        range(1, MasterLookup::MAX_RESULTS),
    ));

    ($this->admin)()
        ->post('/panel/consulta', ['parte' => 'clientes', 'termino' => 'cliente'])
        ->assertSee(MasterLookup::MAX_RESULTS.' resultados')
        ->assertSee('Se muestran los primeros '.MasterLookup::MAX_RESULTS.' y puede haber más. Afina la búsqueda.');
});

it('says when nothing matches', function () {
    ($this->admin)()
        ->post('/panel/consulta', ['parte' => 'clientes', 'termino' => 'zzz'])
        ->assertOk()
        ->assertSee('No encontramos nada con eso.')
        ->assertDontSee('0 resultados');
});

it('rejects invalid input without asking the contract and shows why', function (array $input, string $field, string $message) {
    ($this->admin)()
        ->post('/panel/consulta', $input)
        ->assertUnprocessable()
        ->assertViewIs('panel::consulta')
        ->assertSee($message)
        ->assertSee('aria-describedby="error-'.$field.'"', false)
        ->assertHeader('Cache-Control')
        ->assertSessionMissing('_old_input');

    expect($this->fake->calls)->toBe([]);
})->with([
    'short term' => [['parte' => 'clientes', 'termino' => ' a '], 'termino', 'Escribe al menos 2 caracteres.'],
    'missing term' => [['parte' => 'clientes'], 'termino', 'Escribe un código, un nombre o un NIT.'],
    'long term' => [['parte' => 'clientes', 'termino' => str_repeat('a', 101)], 'termino', 'Escribe máximo 100 caracteres.'],
    'part that cannot be searched' => [['parte' => 'vendedores', 'termino' => 'andina'], 'parte', 'Elige qué buscar de la lista.'],
    'missing part' => [['termino' => 'andina'], 'parte', 'Elige qué buscar de la lista.'],
    'unknown company' => [['parte' => 'clientes', 'empresa' => 'XYZ', 'termino' => 'andina'], 'empresa', 'Elige una empresa de la lista.'],
]);

it('keeps a valid term on the error page without storing it', function () {
    ($this->admin)()
        ->post('/panel/consulta', ['parte' => 'vendedores', 'termino' => '800123456'])
        ->assertUnprocessable()
        ->assertSee('value="800123456"', false)
        ->assertSessionMissing('_old_input');

    expect(json_encode(session()->all()))->not->toContain('800123456');
});

it('tells every response not to store the page', function (string $method, array $input) {
    $response = ($this->admin)()->{$method}('/panel/consulta', $input);

    expect($response->headers->get('Cache-Control'))->toContain('no-store');
})->with([
    'form' => ['get', []],
    'results' => ['post', ['parte' => 'clientes', 'termino' => 'andina']],
    'invalid' => ['post', ['parte' => 'clientes', 'termino' => 'a']],
]);

it('never searches from the URL', function () {
    ($this->admin)()
        ->get('/panel/consulta?parte=clientes&termino=800123456')
        ->assertOk()
        ->assertDontSee('800123456')
        ->assertDontSee('resultados');

    expect($this->fake->calls)->toBe([]);
});

it('neither audits nor stores the term', function () {
    ($this->lookup)([FakeMasterLookup::record()]);

    ($this->admin)()
        ->post('/panel/consulta', ['parte' => 'clientes', 'termino' => '800123456'])
        ->assertOk()
        ->assertSessionMissing('_old_input');

    expect(DB::table('audit_logs')->count())->toBe(0)
        ->and(json_encode(session()->all()))->not->toContain('800123456');
});
