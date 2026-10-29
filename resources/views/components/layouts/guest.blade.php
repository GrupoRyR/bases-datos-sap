{{-- Page without a session (sign-in, no access): a centered card under the logo strip. --}}
@props([
    'title',
])

<!DOCTYPE html>
<html lang="es" data-brand="segurex">
<head>
    <x-layouts.partials.head :title="$title" />
</head>
<body class="min-h-screen">
    <x-layouts.partials.skip-link />

    <main id="contenido" tabindex="-1" class="flex min-h-screen items-center justify-center px-4 py-10">
        <div class="w-full max-w-md overflow-hidden rounded-xl border border-line bg-surface shadow-sm">
            <div class="flex items-center justify-between gap-3 bg-brand-head px-4 py-3 text-on-brand sm:px-6 [&_:focus-visible]:outline-on-brand">
                <x-ui.logo />
                <x-layouts.partials.theme-toggle />
            </div>

            <div class="p-4 sm:p-6">
                <p class="mb-4 text-sm font-semibold text-muted">Bases de datos SAP</p>

                <x-layouts.partials.flash />

                {{ $slot }}
            </div>
        </div>
    </main>
</body>
</html>
