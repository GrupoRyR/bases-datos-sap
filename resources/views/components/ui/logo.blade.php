{{-- Segurex logo as an image, drawn for the --brand-dark gray background; a class sets its height (default h-8). --}}
<img src="{{ asset('img/logo-segurex.png') }}" alt="Segurex LATAM" width="220" height="53" {{ $attributes->class(['w-auto', 'h-8' => ! $attributes->has('class')]) }}>
