{{-- Segurex logo as an image (white variant of the brand manual v2), drawn for the --brand-head background only; a class sets its height (default h-8). --}}
<img src="{{ asset('img/logo-segurex-blanco.png') }}" alt="Segurex LATAM" width="218" height="35" {{ $attributes->class(['w-auto', 'h-8' => ! $attributes->has('class')]) }}>
