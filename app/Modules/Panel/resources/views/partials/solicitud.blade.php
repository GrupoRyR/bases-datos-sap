{{--
    One update request of the history: its number and result, what it asked
    for, when and how long it took, and everyone who asked for it (the
    first created it; the rest joined later). The state is always in words.
--}}
<x-ui.card>
    <div class="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <h2 class="text-base font-semibold text-text">{{ __('panel::solicitudes.solicitud.titulo', ['id' => $request['id']]) }}</h2>
        <x-ui.badge :tone="$request['tone']">{{ $request['state'] }}</x-ui.badge>
    </div>

    <p class="mt-1 text-sm text-text">
        {{ $request['company'] }} · {{ $request['dataset'] }} · {{ $request['scope'] ?? __('panel::solicitudes.solicitud.todo') }}
    </p>

    <ul class="mt-2 text-sm text-muted">
        <li><time datetime="{{ $request['requestedAt']['iso'] }}">{{ __('panel::solicitudes.solicitud.pedida', ['momento' => $request['requestedAt']['text']]) }}</time></li>

        @if ($request['duration'] !== null)
            <li>{{ __('panel::solicitudes.solicitud.tardo', ['duracion' => $request['duration']]) }}</li>
        @endif

        @if ($request['queued'])
            <li>{{ $request['runsAt'] !== null ? __('panel::solicitudes.solicitud.corre', ['cuando' => $request['runsAt']]) : __('panel::solicitudes.solicitud.espera') }}</li>
        @endif
    </ul>

    @if (filled($request['error']))
        <x-ui.alert type="danger" :title="__('panel::solicitudes.solicitud.por_que')" class="mt-3 break-words">{{ $request['error'] }}</x-ui.alert>
    @endif

    @if ($request['requesters'] !== [])
        <h3 class="mt-4 text-sm font-semibold text-text">{{ __('panel::solicitudes.solicitud.quien') }}</h3>

        <ul class="mt-2 flex flex-col gap-2 text-sm">
            @foreach ($request['requesters'] as $requester)
                <li class="break-words">
                    <span class="font-semibold text-text">{{ $requester['origin'] }}</span>
                    <span class="text-muted">· {{ filled($requester['name']) ? $requester['name'].' · ' : '' }}{{ $requester['email'] }}</span>

                    @if ($requester['joinedAt'] !== null)
                        <span class="block text-muted">
                            <time datetime="{{ $requester['joinedAt']['iso'] }}">{{ __('panel::solicitudes.solicitud.se_unio', ['momento' => $requester['joinedAt']['text']]) }}</time>
                        </span>
                    @endif
                </li>
            @endforeach
        </ul>
    @endif
</x-ui.card>
