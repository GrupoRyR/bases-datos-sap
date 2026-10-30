<?php

use Illuminate\Support\MessageBag;
use Illuminate\Support\ViewErrorBag;

it('renders a primary button with the brand button color and white text', function () {
    $this->blade('<x-ui.button type="submit">Guardar</x-ui.button>')
        ->assertSee('<button type="submit"', false)
        ->assertSee('bg-brand-button', false)
        ->assertSee('text-on-brand', false)
        ->assertSee('Guardar');
});

it('renders the secondary and danger variants', function (string $variant, string $class) {
    $this->blade('<x-ui.button :variant="$variant">Acción</x-ui.button>', ['variant' => $variant])
        ->assertSee($class, false)
        ->assertDontSee('bg-brand-button', false);
})->with([
    'secondary' => ['secondary', 'border-line-strong'],
    'danger' => ['danger', 'bg-danger-solid'],
]);

it('renders a link when the button has an href', function () {
    $html = (string) $this->blade('<x-ui.button href="/panel" variant="secondary">Ir al panel</x-ui.button>');

    expect($html)
        ->toContain('<a href="/panel"')
        ->not->toContain('<button')
        ->not->toContain('type=');
});

it('passes extra attributes and classes through', function () {
    $this->blade('<x-ui.button class="w-full" data-test="ok">Enviar</x-ui.button>')
        ->assertSee('w-full', false)
        ->assertSee('data-test="ok"', false);
});

it('renders a card with an optional title', function () {
    $this->blade('<x-ui.card title="Corridas de hoy">Contenido</x-ui.card>')
        ->assertSeeInOrder(['<section', '<h2', 'Corridas de hoy', 'Contenido'], false);

    $this->blade('<x-ui.card>Solo contenido</x-ui.card>')
        ->assertDontSee('<h2', false)
        ->assertSee('Solo contenido');
});

it('renders a page header with description and actions', function () {
    $this->blade(<<<'BLADE'
        <x-ui.page-header title="Solicitudes" description="Lo que piden las apps.">
            <x-slot:actions><a href="/nueva">Nueva</a></x-slot:actions>
        </x-ui.page-header>
        BLADE)
        ->assertSeeInOrder(['<h1', 'Solicitudes', 'Lo que piden las apps.', 'href="/nueva"'], false);

    $this->blade('<x-ui.page-header title="Inicio" />')
        ->assertSee('Inicio')
        ->assertDontSee('<p', false);
});

it('gives alerts the role that matches their urgency', function (string $type, string $role, string $class) {
    $this->blade('<x-ui.alert :type="$type">Mensaje</x-ui.alert>', ['type' => $type])
        ->assertSee("role=\"{$role}\"", false)
        ->assertSee($class, false)
        ->assertSee('Mensaje');
})->with([
    'info' => ['info', 'status', 'bg-info-bg'],
    'success' => ['success', 'status', 'bg-success-bg'],
    'warning' => ['warning', 'alert', 'bg-warning-bg'],
    'danger' => ['danger', 'alert', 'bg-danger-bg'],
]);

it('renders an empty state with a Spanish default title', function () {
    $this->blade('<x-ui.empty />')
        ->assertSee('Aún no hay nada aquí');

    $this->blade('<x-ui.empty title="Sin corridas" description="El robot aún no ha enviado datos." />')
        ->assertSeeInOrder(['Sin corridas', 'El robot aún no ha enviado datos.']);
});

it('renders badges by tone', function (string $tone, string $class) {
    $this->blade('<x-ui.badge :tone="$tone">3</x-ui.badge>', ['tone' => $tone])
        ->assertSee($class, false)
        ->assertSee('3');
})->with([
    'neutral' => ['neutral', 'bg-subtle'],
    'brand' => ['brand', 'text-brand-ink'],
    'success' => ['success', 'bg-success-bg'],
    'danger' => ['danger', 'bg-danger-bg'],
]);

it('renders a field with its label pointing at the text input', function () {
    $html = (string) $this->blade('<x-ui.field label="Nombre" name="nombre" id="campo-nombre" value="Robot" required />');

    expect($html)
        ->toContain('<label for="campo-nombre"')
        ->toContain('Nombre</label>')
        ->toMatch('/<input id="campo-nombre" type="text" name="nombre"/')
        ->toContain('value="Robot"')
        ->toContain('required');
});

it('falls back to the name for the field id', function () {
    $this->blade('<x-ui.field label="Término" name="termino" />')
        ->assertSee('<label for="termino"', false)
        ->assertSee('id="termino"', false)
        ->assertSee('name="termino"', false);
});

it('renders no error state when the field is valid', function () {
    $html = (string) $this->blade('<x-ui.field label="Nombre" name="nombre" />');

    expect($html)
        ->not->toContain('aria-invalid')
        ->not->toContain('aria-describedby')
        ->not->toContain('error-nombre')
        ->not->toContain('text-danger');
});

it('links the validation error to the control', function () {
    $html = (string) $this->withViewErrors(['nombre' => 'Escribe un nombre.'])
        ->blade('<x-ui.field label="Nombre" name="nombre" />');

    expect($html)
        ->toContain('<p id="error-nombre" class="text-sm font-semibold text-danger">Escribe un nombre.</p>')
        ->toContain('aria-invalid="true"')
        ->toContain('aria-describedby="error-nombre"');

    expect(strpos($html, '<label'))->toBeLessThan(strpos($html, 'id="error-nombre"'))
        ->and(strpos($html, 'id="error-nombre"'))->toBeLessThan(strpos($html, '<input'));
});

it('reads an error bag the page passes in instead of the shared one', function () {
    $errors = (new ViewErrorBag)->put('default', new MessageBag(['termino' => 'Escribe al menos 2 caracteres.']));

    $html = (string) $this->blade('<x-ui.field label="Término" name="termino" :errors="$errors" />', ['errors' => $errors]);

    expect($html)
        ->toContain('<p id="error-termino" class="text-sm font-semibold text-danger">Escribe al menos 2 caracteres.</p>')
        ->toContain('aria-invalid="true"')
        ->toContain('aria-describedby="error-termino"')
        ->not->toContain('errors=');
});

it('keeps a passed aria-describedby next to the error', function () {
    $this->withViewErrors(['nombre' => 'Escribe un nombre.'])
        ->blade('<x-ui.field label="Nombre" name="nombre" aria-describedby="ayuda" />')
        ->assertSee('aria-describedby="ayuda error-nombre"', false);

    $this->blade('<x-ui.field label="Llave" id="llave" aria-describedby="llave-aviso" readonly />')
        ->assertSee('aria-describedby="llave-aviso"', false)
        ->assertDontSee('aria-invalid', false);
});

it('paints read-only fields on the subtle color', function () {
    $readonly = (string) $this->blade('<x-ui.field label="Llave" id="llave" value="abc" readonly class="font-mono" />');
    $editable = (string) $this->blade('<x-ui.field label="Nombre" name="nombre" />');

    expect($readonly)
        ->toContain('bg-subtle')
        ->not->toContain('bg-surface')
        ->toContain('font-mono')
        ->not->toContain('name=')
        ->toMatch('/<input id="llave"[^>]*value="abc"[^>]*readonly/');

    expect($editable)
        ->toContain('bg-surface')
        ->not->toContain('bg-subtle');
});

it('renders a select with the slotted options', function () {
    $html = (string) $this->blade(<<<'BLADE'
        <x-ui.field as="select" label="Empresa" name="empresa" id="filtro-empresa">
            <option value="">Todas</option>
            <option value="SDC" selected>Derivados</option>
        </x-ui.field>
        BLADE);

    expect($html)
        ->toContain('<label for="filtro-empresa"')
        ->toMatch('/<select id="filtro-empresa" name="empresa"/')
        ->toContain('<option value="SDC" selected>Derivados</option>')
        ->toContain('bg-surface')
        ->not->toContain('<input')
        ->not->toContain('type=');
});

it('passes extra attributes, the input type and the wrapper classes through', function () {
    $html = (string) $this->blade('<x-ui.field label="Correo" name="correo" type="email" wrapper="min-w-0 flex-1" data-test="ok" autocomplete="off" />');

    expect($html)
        ->toContain('type="email"')
        ->not->toContain('type="text"')
        ->toContain('data-test="ok"')
        ->toContain('autocomplete="off"')
        ->toMatch('/<div class="[^"]*\bmin-w-0\b[^"]*\bflex-1\b[^"]*"/')
        ->toMatch('/<div class="[^"]*\bflex-col gap-1\b/');
});
