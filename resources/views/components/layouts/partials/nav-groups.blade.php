{{-- Navigation items by group; the layout counts the badges once and passes them in. --}}
@props([
    'groups',
    'badges' => [],
])

@foreach ($groups as $group => $items)
    <div class="mb-4">
        <p class="mb-1 px-3 text-xs font-semibold text-muted">{{ $group }}</p>

        <ul class="flex flex-col gap-0.5">
            @foreach ($items as $item)
                @php($active = $item->isActive())
                <li>
                    <a href="{{ $item->url() }}" @if ($active) aria-current="page" @endif
                        @class([
                            'flex min-h-11 items-center justify-between gap-2 rounded-lg px-3 text-sm',
                            'bg-subtle font-semibold text-brand-ink' => $active,
                            'text-text hover:bg-subtle' => ! $active,
                        ])>
                        <span>{{ $item->label }}</span>

                        @if (($badges[$item->key] ?? null) !== null)
                            <x-ui.badge tone="brand">{{ $badges[$item->key] }}</x-ui.badge>
                        @endif
                    </a>
                </li>
            @endforeach
        </ul>
    </div>
@endforeach
