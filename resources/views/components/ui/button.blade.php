{{-- Button or link button. variant: primary (brand), secondary or danger; href renders an <a>. --}}
@props([
    'variant' => 'primary',
    'href' => null,
    'type' => 'button',
])

@php
    $variants = [
        'primary' => 'bg-brand-button text-on-brand hover:brightness-90',
        'secondary' => 'border border-line-strong bg-surface text-text hover:bg-subtle',
        'danger' => 'bg-danger-solid text-on-brand hover:brightness-90',
    ];

    $classes = 'inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold '
        .'transition disabled:cursor-not-allowed disabled:opacity-60 '
        .($variants[$variant] ?? $variants['primary']);
@endphp

@if ($href !== null)
    <a href="{{ $href }}" {{ $attributes->class($classes) }}>{{ $slot }}</a>
@else
    <button type="{{ $type }}" {{ $attributes->class($classes) }}>{{ $slot }}</button>
@endif
