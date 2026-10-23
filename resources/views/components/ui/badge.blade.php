{{-- Small label or counter. tone: neutral, brand, info, success, warning or danger. --}}
@props([
    'tone' => 'neutral',
])

@php
    $tones = [
        'neutral' => 'bg-subtle text-muted',
        'brand' => 'bg-subtle text-brand-ink',
        'info' => 'bg-info-bg text-info',
        'success' => 'bg-success-bg text-success',
        'warning' => 'bg-warning-bg text-warning',
        'danger' => 'bg-danger-bg text-danger',
    ];
@endphp

<span {{ $attributes->class('inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold '.($tones[$tone] ?? $tones['neutral'])) }}>{{ $slot }}</span>
