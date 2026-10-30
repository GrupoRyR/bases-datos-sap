{{--
    GET /panel/actualizar (panel.actualizar), only for core.administrar: the
    company and what to update as two radio groups built from the Sap enums,
    the request rule in one line and the submit button. After the POST the
    layout shows what happened (session('status')).
--}}
<x-layouts.app :title="__('panel::actualizar.titulo')">
    <x-ui.page-header :title="__('panel::actualizar.titulo')" :description="__('panel::actualizar.descripcion')">
        <x-slot:actions>
            <x-ui.button variant="secondary" :href="route('panel.solicitudes')">{{ __('panel::actualizar.historial') }}</x-ui.button>
        </x-slot:actions>
    </x-ui.page-header>

    <x-ui.card>
        <form method="POST" action="{{ route('panel.actualizar.store') }}" class="flex flex-col gap-6">
            @csrf

            @foreach ([
                ['name' => 'empresa', 'legend' => __('panel::actualizar.empresa'), 'options' => $companies, 'columns' => 'sm:grid-cols-2'],
                ['name' => 'datos', 'legend' => __('panel::actualizar.datos'), 'options' => $options, 'columns' => 'md:grid-cols-2'],
            ] as $group)
                <fieldset @error($group['name']) aria-describedby="error-{{ $group['name'] }}" @enderror>
                    <legend class="mb-2 text-sm font-semibold text-text">{{ $group['legend'] }}</legend>

                    @error($group['name'])
                        <p id="error-{{ $group['name'] }}" class="mb-2 text-sm font-semibold text-danger">{{ $message }}</p>
                    @enderror

                    <div class="grid gap-2 {{ $group['columns'] }}">
                        @foreach ($group['options'] as $option)
                            <label class="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border border-line px-3 py-2 text-sm text-text hover:bg-subtle has-checked:border-brand-ink has-checked:bg-subtle">
                                <input type="radio" name="{{ $group['name'] }}" value="{{ $option['value'] }}" required
                                    class="size-5 shrink-0 accent-brand-button" @checked(old($group['name']) === $option['value'])>
                                <span>{{ $option['label'] }}</span>
                            </label>
                        @endforeach
                    </div>
                </fieldset>
            @endforeach

            <p class="text-sm text-muted">{{ __('panel::actualizar.regla') }}</p>

            <div>
                <x-ui.button type="submit" class="w-full sm:w-auto">{{ __('panel::actualizar.boton') }}</x-ui.button>
            </div>
        </form>
    </x-ui.card>
</x-layouts.app>
