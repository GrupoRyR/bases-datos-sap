{{--
    One dataset of a company: when it was last applied, its rows per part
    and its latest run (with the reason when it failed or expired).
--}}
@php($run = $dataset['lastRun'])

<x-ui.card>
    <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 class="text-base font-semibold text-text">{{ $dataset['label'] }}</h3>

        @if ($dataset['appliedAt'] !== null)
            <p class="text-sm text-muted">
                <time datetime="{{ $dataset['appliedAt']['iso'] }}">{{ __('panel::estado.conjunto.actualizado', ['momento' => $dataset['appliedAt']['text']]) }}</time>
            </p>
        @else
            <x-ui.badge>{{ __('panel::estado.conjunto.sin_datos') }}</x-ui.badge>
        @endif
    </div>

    @if ($dataset['rows'] !== [])
        <h4 class="mt-4 text-sm font-semibold text-text">{{ __('panel::estado.conjunto.filas') }}</h4>

        <dl class="mt-2 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
            @foreach ($dataset['rows'] as $row)
                <dt class="text-muted">{{ $row['label'] }}</dt>
                <dd class="text-right font-semibold tabular-nums text-text">{{ $row['count'] }}</dd>
            @endforeach
        </dl>
    @endif

    <h4 class="mt-4 text-sm font-semibold text-text">{{ __('panel::estado.corrida.titulo') }}</h4>

    @if ($run !== null)
        <p class="mt-2 flex flex-wrap items-center gap-2 text-sm">
            <span class="font-semibold text-text">{{ $run['type'] }}</span>
            <x-ui.badge :tone="$run['tone']">{{ $run['state'] }}</x-ui.badge>
        </p>

        <ul class="mt-1 text-sm text-muted">
            <li><time datetime="{{ $run['startedAt']['iso'] }}">{{ __('panel::estado.corrida.empezo', ['momento' => $run['startedAt']['text']]) }}</time></li>

            @if ($run['finishedAt'] !== null)
                <li><time datetime="{{ $run['finishedAt']['iso'] }}">{{ __('panel::estado.corrida.termino', ['momento' => $run['finishedAt']['text']]) }}</time></li>
            @endif
        </ul>

        @if (filled($run['error']))
            <x-ui.alert type="danger" :title="__('panel::estado.corrida.por_que')" class="mt-3 break-words">{{ $run['error'] }}</x-ui.alert>
        @endif
    @else
        <p class="mt-2 text-sm text-muted">{{ __('panel::estado.corrida.ninguna') }}</p>
    @endif
</x-ui.card>
