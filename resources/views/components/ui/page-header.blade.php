{{-- Page title with an optional description and an actions slot. --}}
@props([
    'title',
    'description' => null,
])

<div {{ $attributes->class('mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between') }}>
    <div class="min-w-0">
        <h1 class="text-2xl font-bold text-text">{{ $title }}</h1>

        @if ($description !== null)
            <p class="mt-1 text-brand-text">{{ $description }}</p>
        @endif
    </div>

    @isset($actions)
        <div class="flex flex-wrap gap-2">{{ $actions }}</div>
    @endisset
</div>
