{{--
    One connected app: its name and state in words, the prefix of its key
    (never the key), its dates and its actions. A new key works at once and
    the old one dies; revoking asks first inside a <details>, with no
    JavaScript. A revoked app only offers a new key, which reactivates it.
--}}
<x-ui.card>
    <div class="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
        <h2 class="min-w-0 break-words text-base font-semibold text-text">{{ $app['name'] }}</h2>

        @if ($app['revokedAt'] === null)
            <x-ui.badge tone="success">{{ __('panel::apps.app.activa') }}</x-ui.badge>
        @else
            <x-ui.badge tone="danger">{{ __('panel::apps.app.revocada') }}</x-ui.badge>
        @endif
    </div>

    <ul class="mt-2 text-sm text-muted">
        @if ($app['revokedAt'] !== null)
            <li class="font-semibold text-danger">
                <time datetime="{{ $app['revokedAt']['iso'] }}">{{ __('panel::apps.app.revocada_el', ['momento' => $app['revokedAt']['text']]) }}</time>
            </li>
        @endif
        <li class="break-all font-mono text-text">{{ __('panel::apps.app.llave', ['prefijo' => $app['keyPrefix']]) }}</li>
        <li><time datetime="{{ $app['createdAt']['iso'] }}">{{ __('panel::apps.app.creada', ['momento' => $app['createdAt']['text']]) }}</time></li>
        <li>
            @if ($app['lastUsedAt'] !== null)
                <time datetime="{{ $app['lastUsedAt']['iso'] }}">{{ __('panel::apps.app.ultimo_uso', ['momento' => $app['lastUsedAt']['text']]) }}</time>
            @else
                {{ __('panel::apps.app.sin_uso') }}
            @endif
        </li>
    </ul>

    <div class="mt-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-start">
        <form method="POST" action="{{ route('panel.apps.rotate', $app['id']) }}" class="flex flex-col gap-1">
            @csrf

            @if ($app['revokedAt'] === null)
                <x-ui.button type="submit" variant="secondary" class="w-full sm:w-auto" aria-describedby="rotar-{{ $app['id'] }}">{{ __('panel::apps.app.rotar') }}</x-ui.button>
                <p id="rotar-{{ $app['id'] }}" class="text-xs text-muted">{{ __('panel::apps.app.rotar_aviso') }}</p>
            @else
                <x-ui.button type="submit" variant="secondary" class="w-full sm:w-auto">{{ __('panel::apps.app.reactivar') }}</x-ui.button>
            @endif
        </form>

        @if ($app['revokedAt'] === null)
            <details>
                <summary class="inline-flex min-h-11 w-full cursor-pointer items-center justify-center rounded-lg border border-line-strong bg-surface px-4 py-2 text-sm font-semibold text-danger hover:bg-subtle sm:w-auto">
                    {{ __('panel::apps.app.revocar') }}
                </summary>

                <form method="POST" action="{{ route('panel.apps.revoke', $app['id']) }}" class="mt-3 flex flex-col gap-3 rounded-lg border border-danger bg-danger-bg p-3">
                    @csrf

                    <p class="text-sm text-danger">{{ __('panel::apps.app.revocar_pregunta', ['nombre' => $app['name']]) }}</p>

                    <div>
                        <x-ui.button type="submit" variant="danger" class="w-full sm:w-auto">{{ __('panel::apps.app.revocar_si') }}</x-ui.button>
                    </div>
                </form>
            </details>
        @endif
    </div>
</x-ui.card>
