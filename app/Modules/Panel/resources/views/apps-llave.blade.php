{{--
    The answer to POST /panel/apps and /panel/apps/{app}/llave: the new key,
    shown this once in a read-only field to copy. It is rendered straight
    from the POST with Cache-Control: no-store; the key never goes to the
    session, the audit log or any log.
--}}
<x-layouts.app :title="__('panel::apps.llave.titulo', ['nombre' => $name])">
    <x-ui.page-header :title="__('panel::apps.llave.titulo', ['nombre' => $name])" />

    <x-ui.card>
        <div class="flex flex-col gap-4">
            <div class="flex flex-col gap-1">
                <label for="llave" class="text-sm font-semibold text-text">{{ __('panel::apps.llave.campo') }}</label>
                <input id="llave" type="text" value="{{ $key }}" readonly autocomplete="off" spellcheck="false" aria-describedby="llave-aviso"
                    class="min-h-11 w-full rounded-lg border border-line-strong bg-subtle px-3 font-mono text-sm text-text">
            </div>

            <x-ui.alert type="warning" id="llave-aviso">{{ __('panel::apps.llave.aviso') }}</x-ui.alert>

            <div>
                <x-ui.button variant="secondary" :href="route('panel.apps')" class="w-full sm:w-auto">{{ __('panel::apps.llave.volver') }}</x-ui.button>
            </div>
        </div>
    </x-ui.card>
</x-layouts.app>
