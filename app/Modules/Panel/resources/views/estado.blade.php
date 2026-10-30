{{--
    GET /panel (panel.estado): the stability counter first, then one section
    per company with a card per dataset. StatusController passes plain,
    already formatted data; the order is the one Sap returns.
--}}
<x-layouts.app :title="__('panel::estado.titulo')">
    <x-ui.page-header :title="__('panel::estado.titulo')" :description="__('panel::estado.descripcion')" />

    @include('panel::partials.estabilidad', ['stability' => $stability])

    @forelse ($companies as $company)
        <section aria-labelledby="empresa-{{ $loop->index }}" class="mt-8">
            <h2 id="empresa-{{ $loop->index }}" class="mb-3 text-lg font-bold text-text">{{ $company['label'] }}</h2>

            <div class="grid gap-4 md:grid-cols-2">
                @foreach ($company['datasets'] as $dataset)
                    @include('panel::partials.conjunto', ['dataset' => $dataset])
                @endforeach
            </div>
        </section>
    @empty
        <x-ui.empty class="mt-8" :title="__('panel::estado.vacio.titulo')" :description="__('panel::estado.vacio.detalle')" />
    @endforelse
</x-layouts.app>
