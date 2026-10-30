{{--
    GET /panel/apps (panel.apps), only for core.administrar: the form to
    connect a new app and one card per app, ordered by name, with only the
    prefix of its key. After a revoke the layout shows session('status').
--}}
<x-layouts.app :title="__('panel::apps.titulo')">
    <x-ui.page-header :title="__('panel::apps.titulo')" :description="__('panel::apps.descripcion')" />

    <x-ui.card :title="__('panel::apps.nueva.titulo')" class="mb-6">
        <form method="POST" action="{{ route('panel.apps.store') }}" class="flex flex-col gap-4 sm:flex-row sm:items-end">
            @csrf

            <x-ui.field :label="__('panel::apps.nueva.nombre')" name="nombre" wrapper="min-w-0 flex-1"
                value="{{ old('nombre') }}" required maxlength="100" autocomplete="off" />

            <x-ui.button type="submit" class="w-full sm:w-auto">{{ __('panel::apps.nueva.boton') }}</x-ui.button>
        </form>
    </x-ui.card>

    @if ($apps === [])
        <x-ui.empty :title="__('panel::apps.vacio')" />
    @else
        <ul class="flex flex-col gap-4">
            @foreach ($apps as $app)
                <li>
                    @include('panel::partials.app', ['app' => $app])
                </li>
            @endforeach
        </ul>
    @endif
</x-layouts.app>
