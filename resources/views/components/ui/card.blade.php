{{-- Content block on the surface color, with an optional title. --}}
@props([
    'title' => null,
])

<section {{ $attributes->class('rounded-xl border border-line bg-surface p-4 sm:p-6') }}>
    @if ($title !== null)
        <h2 class="mb-3 text-base font-semibold text-text">{{ $title }}</h2>
    @endif

    {{ $slot }}
</section>
