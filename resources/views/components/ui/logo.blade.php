{{-- Segurex logo as an image (gray-on-dark variant, the gestor de cartera's SVG), drawn for the --brand-dark background; a class sets its height (default h-8). --}}
<img src="{{ asset('img/logo-segurex.svg') }}" alt="Segurex LATAM" width="220" height="35" {{ $attributes->class(['w-auto', 'h-8' => ! $attributes->has('class')]) }}>
