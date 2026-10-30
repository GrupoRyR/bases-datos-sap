{{--
    GET /panel/solicitudes (panel.solicitudes): a GET filter form, then one
    card per request, newest first, and the page links. RequestHistoryController
    passes plain, already formatted data; the page links keep the filters.
--}}
<x-layouts.app :title="__('panel::solicitudes.titulo')">
    <x-ui.page-header :title="__('panel::solicitudes.titulo')" :description="__('panel::solicitudes.descripcion')" />

    <form method="GET" action="{{ route('panel.solicitudes') }}" aria-label="{{ __('panel::solicitudes.filtros.titulo') }}"
        class="mb-6 grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <x-ui.field as="select" :label="__('panel::solicitudes.filtros.empresa')" name="empresa" id="filtro-empresa">
            <option value="">{{ __('panel::solicitudes.filtros.todas') }}</option>
            @foreach ($filters['companies'] as $option)
                <option value="{{ $option['value'] }}" @selected($filters['empresa'] === $option['value'])>{{ $option['label'] }}</option>
            @endforeach
        </x-ui.field>

        <x-ui.field as="select" :label="__('panel::solicitudes.filtros.conjunto')" name="conjunto" id="filtro-conjunto">
            <option value="">{{ __('panel::solicitudes.filtros.todos') }}</option>
            @foreach ($filters['datasets'] as $option)
                <option value="{{ $option['value'] }}" @selected($filters['conjunto'] === $option['value'])>{{ $option['label'] }}</option>
            @endforeach
        </x-ui.field>

        <x-ui.button type="submit" variant="secondary">{{ __('panel::solicitudes.filtros.boton') }}</x-ui.button>
    </form>

    @if ($requests === [])
        <x-ui.empty :title="__('panel::solicitudes.vacio')" />
    @else
        <ol class="flex flex-col gap-4">
            @foreach ($requests as $request)
                <li>
                    @include('panel::partials.solicitud', ['request' => $request])
                </li>
            @endforeach
        </ol>
    @endif

    @if ($pages['last'] > 1)
        <nav aria-label="{{ __('panel::solicitudes.paginas.titulo') }}" class="mt-6 flex flex-wrap items-center justify-between gap-3">
            <p class="text-sm text-muted">{{ __('panel::solicitudes.paginas.pagina', ['pagina' => $pages['current'], 'total' => $pages['last']]) }}</p>

            <div class="flex flex-wrap gap-2">
                @if ($pages['newer'] !== null)
                    <x-ui.button variant="secondary" :href="$pages['newer']" rel="prev">{{ __('panel::solicitudes.paginas.recientes') }}</x-ui.button>
                @endif

                @if ($pages['older'] !== null)
                    <x-ui.button variant="secondary" :href="$pages['older']" rel="next">{{ __('panel::solicitudes.paginas.anteriores') }}</x-ui.button>
                @endif
            </div>
        </nav>
    @endif
</x-layouts.app>
