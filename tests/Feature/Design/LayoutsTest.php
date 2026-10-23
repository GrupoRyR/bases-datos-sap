<?php

use App\Models\User;
use App\Support\Navigation\NavItem;
use App\Support\Navigation\NavRegistry;
use Illuminate\Support\Facades\Blade;
use Illuminate\Support\Facades\Gate;
use Illuminate\Support\Facades\Route;

beforeEach(function () {
    Route::middleware('web')->get('/design/allowed', fn () => Blade::render(
        '<x-layouts.app title="Permitido">Contenido permitido</x-layouts.app>',
    ))->name('design.allowed');
    Route::get('/design/denied', fn () => 'denied')->name('design.denied');
    Route::getRoutes()->refreshNameLookups();

    Gate::define('design.view', fn (User $user): bool => true);
    Gate::define('design.secret', fn (User $user): bool => false);

    app(NavRegistry::class)->add(
        new NavItem(key: 'design.allowed', label: 'Elemento permitido', route: 'design.allowed', permission: 'design.view', group: 'Pruebas', mobile: true),
        new NavItem(key: 'design.denied', label: 'Elemento negado', route: 'design.denied', permission: 'design.secret', group: 'Pruebas', mobile: true),
    );

    $this->user = User::factory()->make(['name' => 'Ana Pérez']);
});

it('renders the app layout with the Segurex brand, title and theme support', function () {
    $this->blade('<x-layouts.app title="Inicio">Hola</x-layouts.app>')
        ->assertSee('<html lang="es" data-brand="segurex">', false)
        ->assertSee('<meta name="color-scheme" content="light dark">', false)
        ->assertSee('<title>Inicio · Bases de datos SAP</title>', false)
        ->assertSee("localStorage.getItem('bases-sap-theme')", false)
        ->assertSee('data-theme-toggle', false)
        ->assertSee('aria-label="Tema: sistema"', false)
        ->assertSee('Bases de datos SAP')
        ->assertSee('Hola');
});

it('shows the logo as an image on the dark header', function () {
    $this->blade('<x-layouts.app title="Inicio">Hola</x-layouts.app>')
        ->assertSeeInOrder(['<header', 'bg-brand-dark', '<img', '/img/logo-segurex.png', 'alt="Segurex LATAM"'], false);
});

it('lets the caller set the logo height', function () {
    $this->blade('<x-ui.logo />')->assertSee('class="w-auto h-8"', false);

    $this->blade('<x-ui.logo class="h-6" />')
        ->assertSee('class="w-auto h-6"', false)
        ->assertDontSee('h-8', false);
});

it('starts with a skip link to the main content', function () {
    $this->blade('<x-layouts.app title="Inicio">Hola</x-layouts.app>')
        ->assertSeeInOrder(['<body', 'href="#contenido"', 'Saltar al contenido', '<main id="contenido"'], false);
});

it('shows guests no navigation and no user', function () {
    $this->blade('<x-layouts.app title="Inicio">Hola</x-layouts.app>')
        ->assertDontSee('Elemento permitido')
        ->assertDontSee('Menú principal')
        ->assertDontSee('Cerrar sesión');
});

it('shows the user only the items the Gate allows, in the menu and the bottom bar', function () {
    $this->actingAs($this->user)
        ->blade('<x-layouts.app title="Inicio">Hola</x-layouts.app>')
        ->assertSee('Ana Pérez')
        ->assertSeeInOrder(['Menú principal', 'Pruebas', 'Elemento permitido', 'Accesos rápidos', 'Elemento permitido'])
        ->assertDontSee('Elemento negado');
});

it('marks the item of the current page as active', function () {
    $html = $this->actingAs($this->user)->get('/design/allowed')->assertOk()->getContent();

    expect($html)
        ->toContain('aria-current="page"')
        ->toContain('Contenido permitido');
});

it('marks nothing as active on other pages', function () {
    $this->actingAs($this->user)
        ->blade('<x-layouts.app title="Inicio">Hola</x-layouts.app>')
        ->assertDontSee('aria-current', false);
});

it('posts the logout form to the core.logout route when it exists', function () {
    if (! Route::has('core.logout')) {
        Route::post('/salir', fn () => 'out')->name('core.logout');
        Route::getRoutes()->refreshNameLookups();
    }

    $this->actingAs($this->user)
        ->blade('<x-layouts.app title="Inicio">Hola</x-layouts.app>')
        ->assertSeeInOrder(['<form method="POST" action="'.route('core.logout').'"', 'name="_token"', 'Cerrar sesión'], false);
});

it('shows the flash messages', function () {
    session(['status' => 'Cambios guardados.', 'error' => 'No se pudo guardar.']);

    $this->blade('<x-layouts.app title="Inicio">Hola</x-layouts.app>')
        ->assertSeeInOrder(['role="status"', 'Cambios guardados.', 'role="alert"', 'No se pudo guardar.'], false);
});

it('renders the guest layout with the logo, the toggle and the content', function () {
    session(['error' => 'Tu cuenta no tiene acceso.']);

    $this->blade('<x-layouts.guest title="Ingresar">Formulario</x-layouts.guest>')
        ->assertSee('<html lang="es" data-brand="segurex">', false)
        ->assertSee('<title>Ingresar · Bases de datos SAP</title>', false)
        ->assertSeeInOrder(['href="#contenido"', 'Saltar al contenido', '<main id="contenido"', 'bg-brand-dark', 'alt="Segurex LATAM"', 'aria-label="Tema: sistema"', 'Tu cuenta no tiene acceso.', 'Formulario'], false)
        ->assertDontSee('Menú principal');
});
