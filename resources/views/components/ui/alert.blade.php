{{-- Message box. type: info, success (role status) or warning, danger (role alert). --}}
@props([
    'type' => 'info',
    'title' => null,
])

@php
    $tones = [
        'info' => 'border-info bg-info-bg text-info',
        'success' => 'border-success bg-success-bg text-success',
        'warning' => 'border-warning bg-warning-bg text-warning',
        'danger' => 'border-danger bg-danger-bg text-danger',
    ];

    $type = array_key_exists($type, $tones) ? $type : 'info';
    $role = in_array($type, ['warning', 'danger'], true) ? 'alert' : 'status';
@endphp

<div role="{{ $role }}" {{ $attributes->class('rounded-lg border-l-4 px-4 py-3 text-sm '.$tones[$type]) }}>
    @if ($title !== null)
        <p class="font-semibold">{{ $title }}</p>
    @endif

    <div>{{ $slot }}</div>
</div>
