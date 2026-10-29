<?php

use Illuminate\Support\Facades\File;

/**
 * Blade views of the base and of every module.
 *
 * @return list<string>
 */
function designBladeFiles(): array
{
    $files = [];

    foreach ([resource_path('views'), app_path('Modules')] as $directory) {
        foreach (File::allFiles($directory) as $file) {
            if (str_ends_with($file->getFilename(), '.blade.php')) {
                $files[] = $file->getPathname();
            }
        }
    }

    return $files;
}

it('loads no external font', function (string $path) {
    $contents = File::get(base_path($path));

    expect($contents)
        ->not->toContain('fonts.bunny.net')
        ->not->toContain('fonts.googleapis.com')
        ->not->toContain('Instrument Sans');
})->with(['resources/css/app.css', 'vite.config.js']);

it('uses Helvetica and Arial for the whole interface', function () {
    expect(File::get(resource_path('css/app.css')))
        ->toContain("--font-sans: Helvetica, Arial, 'Helvetica Neue', sans-serif;");
});

it('declares the Segurex brand variables', function () {
    $css = File::get(resource_path('css/app.css'));

    expect($css)->toContain(":root[data-brand='segurex']");

    foreach (['accent', 'button', 'ink', 'text', 'tint', 'head', 'head-fg', 'head-muted'] as $name) {
        expect($css)->toContain("--brand-{$name}:")
            ->toContain("--color-brand-{$name}: var(--brand-{$name});");
    }
});

it('scans the module views for utility classes', function () {
    expect(File::get(resource_path('css/app.css')))
        ->toContain("@source '../views/**/*.blade.php';")
        ->toContain("@source '../../app/Modules/**/resources/views/**/*.blade.php';");
});

it('keeps fonts and brand colors out of the views', function () {
    $forbidden = ['fonts.bunny.net', 'fonts.googleapis.com', '#f26522', '#c6531c', '#943e15', '#58595b'];

    foreach (designBladeFiles() as $file) {
        $contents = strtolower(File::get($file));

        foreach ($forbidden as $needle) {
            expect(str_contains($contents, $needle))->toBeFalse("{$file} contains {$needle}");
        }
    }
});
