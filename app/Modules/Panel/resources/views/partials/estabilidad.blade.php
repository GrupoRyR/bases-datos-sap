{{--
    The stability counter of plan section 6: the streak, the last days
    (today first) with their state in words, what failed on the unstable
    days and the criterion that TI checks by hand.
--}}
@php
    $failedDays = array_values(array_filter($stability['days'], fn (array $day): bool => $day['state'] === 'con_fallas'));
@endphp

<x-ui.card :title="__('panel::estado.estabilidad.titulo')">
    <p class="text-3xl font-bold text-text">
        {{ __('panel::estado.estabilidad.contador', ['dias' => $stability['stableDays'], 'meta' => $stability['targetDays']]) }}
    </p>
    <p class="mt-1 text-sm text-muted">{{ __('panel::estado.estabilidad.detalle') }}</p>

    <h3 id="franja-estable" class="mt-4 text-sm font-semibold text-text">
        {{ __('panel::estado.estabilidad.franja', ['dias' => count($stability['days'])]) }}
    </h3>

    <ol aria-labelledby="franja-estable" class="mt-2 grid grid-cols-3 gap-2 sm:grid-cols-5 md:grid-cols-7">
        @foreach ($stability['days'] as $day)
            <li @class([
                'flex flex-col items-center rounded-lg px-2 py-2 text-center text-sm',
                'bg-success-bg text-success' => $day['state'] === 'estable',
                'bg-danger-bg text-danger' => $day['state'] === 'con_fallas',
                'bg-subtle text-muted' => $day['state'] === 'en_curso',
            ])>
                <time datetime="{{ $day['iso'] }}">{{ $day['date'] }}</time>
                <span class="text-xs font-semibold">{{ __('panel::estado.estabilidad.'.$day['state']) }}</span>
            </li>
        @endforeach
    </ol>

    @if ($failedDays !== [])
        <details class="mt-4">
            <summary class="flex min-h-11 cursor-pointer items-center text-sm font-semibold text-text">
                {{ __('panel::estado.estabilidad.problemas') }}
            </summary>

            <ul class="mt-2 flex flex-col gap-3 text-sm">
                @foreach ($failedDays as $day)
                    <li>
                        <p class="font-semibold text-text"><time datetime="{{ $day['iso'] }}">{{ $day['date'] }}</time></p>
                        <ul class="list-disc pl-5 text-muted">
                            @foreach ($day['problems'] as $problem)
                                <li>{{ $problem }}</li>
                            @endforeach
                        </ul>
                    </li>
                @endforeach
            </ul>
        </details>
    @endif

    <p class="mt-4 text-sm text-muted">{{ __('panel::estado.estabilidad.a_mano') }}</p>
</x-ui.card>
