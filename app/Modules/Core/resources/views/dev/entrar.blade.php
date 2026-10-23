{{--
    GET /dev/entrar (core.dev.entrar): only in local, from this machine.
    Lists the active users with a role; each one signs in with a POST.
--}}
<x-layouts.guest :title="__('core::ingreso.demo.titulo')">
    <h1 class="text-xl font-bold text-text">{{ __('core::ingreso.demo.encabezado') }}</h1>
    <p class="mt-2 text-sm text-muted">{{ __('core::ingreso.demo.detalle') }}</p>

    @if ($users->isEmpty())
        <x-ui.empty class="mt-6" :title="__('core::ingreso.demo.vacio')" />
    @else
        <ul class="mt-6 space-y-3">
            @foreach ($users as $user)
                <li>
                    <form method="POST" action="{{ route('core.dev.entrar.usuario', $user) }}" class="rounded-lg border border-line p-4">
                        @csrf
                        <p class="font-semibold text-text">{{ $user->name }}</p>
                        <p class="text-sm text-muted">{{ $user->email }}</p>
                        <x-ui.badge tone="brand" class="mt-2">{{ $user->role?->label() }}</x-ui.badge>
                        <x-ui.button type="submit" class="mt-3 w-full">{{ __('core::ingreso.demo.boton', ['nombre' => $user->name]) }}</x-ui.button>
                    </form>
                </li>
            @endforeach
        </ul>
    @endif
</x-layouts.guest>
