{{--
    One record found by the lookup: its name and state, its code, NIT (only
    customers and suppliers have one) and company, when it changed in SAP and
    when it arrived here. The state is always in words.
--}}
<x-ui.card>
    <div class="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
        <h3 class="min-w-0 break-words text-base font-semibold text-text">{{ $record['name'] }}</h3>
        <x-ui.badge :tone="$record['active'] ? 'success' : 'neutral'">{{ $record['state'] }}</x-ui.badge>
    </div>

    <p class="mt-1 break-words text-sm text-text">
        {{ $record['code'] }}@if ($record['taxId'] !== null) · {{ $record['taxId'] }}@endif · {{ $record['company'] }}
    </p>

    <ul class="mt-2 text-sm text-muted">
        <li>
            @if ($record['updatedInSap'] !== null)
                <time datetime="{{ $record['updatedInSap']['iso'] }}">{{ $record['updatedInSap']['text'] }}</time>
            @else
                {{ __('panel::consulta.registro.sin_cambio') }}
            @endif
        </li>
        <li><time datetime="{{ $record['syncedAt']['iso'] }}">{{ $record['syncedAt']['text'] }}</time></li>
    </ul>
</x-ui.card>
