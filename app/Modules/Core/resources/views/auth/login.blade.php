{{--
    GET /login (core.login): the sign-in page. The guest layout shows the
    flashed status (after signing out) or error (a rejected or failed sign-in).
--}}
<x-layouts.guest :title="__('core::ingreso.login.titulo')">
    <h1 class="text-xl font-bold text-text">{{ __('core::ingreso.login.encabezado') }}</h1>
    <p class="mt-2 text-sm text-muted">{{ __('core::ingreso.login.detalle') }}</p>

    <x-ui.button :href="route('core.auth.redirect')" class="mt-6 w-full">
        {{ __('core::ingreso.login.boton') }}
    </x-ui.button>
</x-layouts.guest>
