{{-- Signed-in page: header with the logo, navigation from NavRegistry, flash messages and the slot. --}}
@props([
    'title',
])

@php
    $user = auth()->user();
    $menu = app(\App\Support\Navigation\NavRegistry::class)->menuFor($user);
    $badges = [];

    foreach ($menu['groups'] as $items) {
        foreach ($items as $item) {
            $badges[$item->key] = $item->badgeCount();
        }
    }
@endphp

<!DOCTYPE html>
<html lang="es" data-brand="segurex">
<head>
    <x-layouts.partials.head :title="$title" />
</head>
<body class="min-h-screen">
    <x-layouts.partials.skip-link />

    <header class="bg-brand-dark text-on-brand [&_:focus-visible]:outline-on-brand">
        <div class="mx-auto flex max-w-7xl items-center gap-3 px-4 py-2">
            <a href="{{ url('/') }}" class="shrink-0 rounded">
                <x-ui.logo class="h-7 sm:h-8" />
            </a>

            <span class="hidden truncate font-semibold sm:block">Bases de datos SAP</span>

            <div class="ml-auto flex items-center gap-2">
                <x-layouts.partials.theme-toggle />

                @if ($user !== null)
                    <span class="hidden max-w-48 truncate text-sm md:block">{{ $user->name }}</span>

                    @if (Route::has('core.logout'))
                        <form method="POST" action="{{ route('core.logout') }}">
                            @csrf
                            <button type="submit" class="inline-flex min-h-11 items-center rounded-lg px-3 text-sm font-semibold hover:bg-on-brand/10">
                                <span class="sm:hidden">Salir</span>
                                <span class="hidden sm:inline">Cerrar sesión</span>
                            </button>
                        </form>
                    @endif
                @endif
            </div>
        </div>
    </header>

    @if ($menu['groups'] !== [])
        {{-- Phones and tablets: the full menu folds into a disclosure that works without JavaScript. --}}
        <details class="border-b border-line bg-surface lg:hidden">
            <summary class="mx-auto flex min-h-11 max-w-7xl cursor-pointer items-center px-4 text-sm font-semibold">Menú</summary>

            <nav aria-label="Menú principal" class="mx-auto max-w-7xl px-2 pb-2">
                <x-layouts.partials.nav-groups :groups="$menu['groups']" :badges="$badges" />
            </nav>
        </details>
    @endif

    <div class="mx-auto flex max-w-7xl gap-6 px-4">
        @if ($menu['groups'] !== [])
            <nav aria-label="Menú principal" class="hidden w-60 shrink-0 py-6 lg:block">
                <x-layouts.partials.nav-groups :groups="$menu['groups']" :badges="$badges" />
            </nav>
        @endif

        <main id="contenido" tabindex="-1" @class(['min-w-0 flex-1 py-6', 'pb-24 lg:pb-6' => $menu['mobile'] !== []])>
            <x-layouts.partials.flash />

            {{ $slot }}
        </main>
    </div>

    @if ($menu['mobile'] !== [])
        <nav aria-label="Accesos rápidos" class="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface lg:hidden">
            <ul class="flex">
                @foreach ($menu['mobile'] as $item)
                    @php($active = $item->isActive())
                    <li class="min-w-0 flex-1">
                        <a href="{{ $item->url() }}" @if ($active) aria-current="page" @endif
                            @class([
                                'flex min-h-14 items-center justify-center px-1 text-center text-xs',
                                'font-semibold text-brand-ink' => $active,
                                'text-muted' => ! $active,
                            ])>{{ $item->label }}</a>
                    </li>
                @endforeach
            </ul>
        </nav>
    @endif
</body>
</html>
