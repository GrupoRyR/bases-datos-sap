{{-- Empty state: a title, an optional description and optional actions in the slot. --}}
@props([
    'title' => 'Aún no hay nada aquí',
    'description' => null,
])

<div {{ $attributes->class('rounded-xl border border-dashed border-line-strong bg-surface px-4 py-10 text-center') }}>
    <p class="text-base font-semibold text-text">{{ $title }}</p>

    @if ($description !== null)
        <p class="mt-1 text-sm text-muted">{{ $description }}</p>
    @endif

    @if ($slot->isNotEmpty())
        <div class="mt-4 flex justify-center gap-2">{{ $slot }}</div>
    @endif
</div>
