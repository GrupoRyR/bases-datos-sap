{{--
    GET and POST /panel/consulta (panel.consulta, panel.consulta.buscar): the
    search form (what to look up, the company and the term) and, after a
    valid POST, one card per record. Support\LookupPage passes the values to
    fill the form again and the errors, never through the session: the term
    can be a NIT or a name.
--}}
<x-layouts.app :title="__('panel::consulta.titulo')">
    <x-ui.page-header :title="__('panel::consulta.titulo')" :description="__('panel::consulta.descripcion')" />

    <x-ui.card>
        <form method="POST" action="{{ route('panel.consulta.buscar') }}" class="flex flex-col gap-6">
            @csrf

            @foreach ([
                ['name' => 'parte', 'legend' => __('panel::consulta.parte'), 'options' => $parts, 'default' => $parts[0]['value'] ?? ''],
                ['name' => 'empresa', 'legend' => __('panel::consulta.empresa'), 'options' => $companies, 'default' => ''],
            ] as $group)
                @php($chosen = $values[$group['name']] === '' ? $group['default'] : $values[$group['name']])

                <fieldset @error($group['name']) aria-describedby="error-{{ $group['name'] }}" @enderror>
                    <legend class="mb-2 text-sm font-semibold text-text">{{ $group['legend'] }}</legend>

                    @error($group['name'])
                        <p id="error-{{ $group['name'] }}" class="mb-2 text-sm font-semibold text-danger">{{ $message }}</p>
                    @enderror

                    <div class="grid gap-2 sm:grid-cols-3">
                        @foreach ($group['options'] as $option)
                            <label class="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border border-line px-3 py-2 text-sm text-text hover:bg-subtle has-checked:border-brand-ink has-checked:bg-subtle">
                                <input type="radio" name="{{ $group['name'] }}" value="{{ $option['value'] }}" required
                                    class="size-5 shrink-0 accent-brand-button" @checked($chosen === $option['value'])>
                                <span>{{ $option['label'] }}</span>
                            </label>
                        @endforeach
                    </div>
                </fieldset>
            @endforeach

            <div class="flex flex-col gap-1">
                <label for="termino" class="text-sm font-semibold text-text">{{ __('panel::consulta.termino') }}</label>

                @error('termino')
                    <p id="error-termino" class="text-sm font-semibold text-danger">{{ $message }}</p>
                @enderror

                <input id="termino" type="text" name="termino" value="{{ $values['termino'] }}" required minlength="2" maxlength="100"
                    autocomplete="off" spellcheck="false"
                    class="min-h-11 w-full rounded-lg border border-line-strong bg-surface px-3 text-sm text-text"
                    @error('termino') aria-invalid="true" aria-describedby="error-termino" @enderror>
            </div>

            <div>
                <x-ui.button type="submit" class="w-full sm:w-auto">{{ __('panel::consulta.boton') }}</x-ui.button>
            </div>
        </form>
    </x-ui.card>

    @if ($records === [])
        <x-ui.empty :title="__('panel::consulta.vacio')" class="mt-6" role="status" />
    @elseif ($records !== null)
        <section aria-labelledby="resultados" class="mt-6">
            <h2 id="resultados" class="mb-3 text-lg font-semibold text-text">{{ trans_choice('panel::consulta.resultados', count($records)) }}</h2>

            @if ($capped)
                <x-ui.alert type="info" class="mb-4">{{ __('panel::consulta.tope', ['max' => count($records)]) }}</x-ui.alert>
            @endif

            <ol class="flex flex-col gap-4">
                @foreach ($records as $record)
                    <li>
                        @include('panel::partials.registro', ['record' => $record])
                    </li>
                @endforeach
            </ol>
        </section>
    @endif
</x-layouts.app>
