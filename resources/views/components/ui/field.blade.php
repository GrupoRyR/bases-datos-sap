{{-- Form field: label, validation error and a text input or, with as="select", a select whose options go in the slot. errors: a page's own bag, else the shared one. --}}
@props([
    'label',
    'name' => null,
    'id' => null,
    'as' => 'input',
    'wrapper' => null,
    'errors' => null,
])

@php
    $id ??= $name;
    $invalid = $name !== null && $errors !== null && $errors->has($name);

    $describedBy = implode(' ', array_filter([
        $attributes->get('aria-describedby'),
        $invalid ? "error-{$name}" : null,
    ]));

    $classes = 'min-h-11 w-full rounded-lg border border-line-strong '
        .($attributes->get('readonly') ? 'bg-subtle' : 'bg-surface')
        .' px-3 text-sm text-text';

    // Own attributes first (id, type, name, class, aria-*), then everything passed in, in its order.
    $control = $attributes->except(['type', 'aria-describedby'])->merge(array_filter([
        'id' => $id,
        'type' => $as === 'select' ? null : $attributes->get('type', 'text'),
        'name' => $name,
        'class' => $classes,
        'aria-invalid' => $invalid ? 'true' : null,
        'aria-describedby' => $describedBy,
    ], fn (mixed $value): bool => $value !== null && $value !== ''));
@endphp

<div class="{{ trim('flex flex-col gap-1 '.$wrapper) }}">
    <label for="{{ $id }}" class="text-sm font-semibold text-text">{{ $label }}</label>

    @if ($invalid)
        <p id="error-{{ $name }}" class="text-sm font-semibold text-danger">{{ $errors->first($name) }}</p>
    @endif

    @if ($as === 'select')
        <select {{ $control }}>
            {{ $slot }}
        </select>
    @else
        <input {{ $control }}>
    @endif
</div>
