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
            <x-ui.field :label="__('panel::apps.llave.campo')" id="llave" value="{{ $key }}" readonly autocomplete="off" spellcheck="false"
                aria-describedby="llave-aviso" class="font-mono" />

            <x-ui.alert type="warning" id="llave-aviso">{{ __('panel::apps.llave.aviso') }}</x-ui.alert>

            <div>
                <x-ui.button variant="secondary" :href="route('panel.apps')" class="w-full sm:w-auto">{{ __('panel::apps.llave.volver') }}</x-ui.button>
            </div>
        </div>
    </x-ui.card>
</x-layouts.app>
