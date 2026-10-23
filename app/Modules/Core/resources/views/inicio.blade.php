{{--
    GET / (core.inicio): the home of a user with a role. The app layout
    already has the logout button in its header.
--}}
<x-layouts.app :title="__('core::ingreso.inicio.titulo')">
    <x-ui.page-header
        :title="__('core::ingreso.inicio.saludo', ['nombre' => $user->name])"
        :description="__('core::ingreso.inicio.rol', ['rol' => $user->role?->label()])"
    />
</x-layouts.app>
