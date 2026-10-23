{{--
    GET /sin-acceso (core.sin-acceso): a signed-in user without a role.
--}}
<x-layouts.guest :title="__('core::ingreso.sin_acceso.titulo')">
    <h1 class="text-xl font-bold text-text">{{ __('core::ingreso.sin_acceso.encabezado') }}</h1>
    <p class="mt-2 text-sm text-muted">{{ __('core::ingreso.sin_acceso.detalle', ['correo' => $user?->email]) }}</p>

    <form method="POST" action="{{ route('core.logout') }}" class="mt-6">
        @csrf
        <x-ui.button type="submit" variant="secondary" class="w-full">{{ __('core::ingreso.salir') }}</x-ui.button>
    </form>
</x-layouts.guest>
