<?php

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
