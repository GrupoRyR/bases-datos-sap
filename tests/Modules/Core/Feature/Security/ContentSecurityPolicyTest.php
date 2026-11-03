<?php

use Illuminate\Foundation\Vite as FoundationVite;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Route;
use Illuminate\Support\Facades\Vite;
use Illuminate\Support\HtmlString;
use Symfony\Component\Finder\Finder;

/*
| Content-Security-Policy of every response (audit S-04). The nonce is the one
| Vite puts on its script tags and the one inline scripts must carry, so the
| test route answers it for the test to compare with the header.
*/

/**
 * A Vite that renders no tags, like withoutVite(), but keeps the hot file:
 * the policy is skipped while the dev server runs, and the default public/hot
 * would exist whenever someone runs "npm run dev" next to the suite.
 */
function coreCspVite(string $hotFile): FoundationVite
{
    $vite = new class extends FoundationVite
    {
        public function __invoke($entrypoints, $buildDirectory = null)
        {
            return new HtmlString('');
        }
    };

    return $vite->useHotFile($hotFile);
}

/**
 * The directives of a Content-Security-Policy header, by name.
 *
 * @return array<string, list<string>>
 */
function coreCspDirectives(string $header): array
{
    $directives = [];

    foreach (array_filter(array_map(trim(...), explode(';', $header))) as $directive) {
        $parts = preg_split('/\s+/', $directive) ?: [];
        $directives[(string) array_shift($parts)] = $parts;
    }

    return $directives;
}

beforeEach(function () {
    Vite::swap(coreCspVite(storage_path('framework/testing/vite-not-running.hot')));

    Route::middleware('web')->get('/_test/nonce', fn () => (string) Vite::cspNonce());
    Route::middleware('api')->get('/api/_test/json', fn () => response()->json(['ok' => true]));
});

it('sends a content security policy with the nonce of the request', function () {
    $response = $this->get('/_test/nonce')->assertOk();
    $nonce = $response->getContent();

    expect($nonce)->not->toBe('')
        ->and(coreCspDirectives((string) $response->headers->get('Content-Security-Policy'))['script-src'])
        ->toBe(["'self'", "'nonce-{$nonce}'"]);
});

it('uses a new nonce on every request', function () {
    expect($this->get('/_test/nonce')->getContent())->not->toBe($this->get('/_test/nonce')->getContent());
});

it('never allows eval', function () {
    $response = $this->get('/_test/nonce')->assertHeader('Content-Security-Policy');

    expect((string) $response->headers->get('Content-Security-Policy'))->not->toContain("'unsafe-eval'");
});

it('allows only the app itself to load resources, frame the page or receive forms', function () {
    $directives = coreCspDirectives((string) $this->get('/_test/nonce')->headers->get('Content-Security-Policy'));

    expect($directives)->toBe([
        'default-src' => ["'self'"],
        'script-src' => $directives['script-src'],
        // The framework's error pages print their CSS in a <style> block.
        'style-src' => ["'self'", "'unsafe-inline'"],
        'img-src' => ["'self'", 'data:'],
        'font-src' => ["'self'"],
        'connect-src' => ["'self'"],
        'manifest-src' => ["'self'"],
        'worker-src' => ["'self'"],
        'object-src' => ["'none'"],
        'base-uri' => ["'self'"],
        'form-action' => ["'self'"],
        'frame-ancestors' => ["'none'"],
    ]);
});

it('puts the nonce of the header on the inline script of the page', function () {
    $response = $this->get('/login')->assertOk();
    $directives = coreCspDirectives((string) $response->headers->get('Content-Security-Policy'));
    $nonce = substr($directives['script-src'][1], strlen("'nonce-"), -1);

    expect($nonce)->not->toBe('')
        ->and($response->getContent())->toContain('<script nonce="'.$nonce.'">');
});

it('protects every response, including redirects, errors and the API', function (string $uri, int $status) {
    // The router sorts auth ahead of the "web" group, so the guest redirect
    // only gets the header from global middleware.
    $this->get($uri)
        ->assertStatus($status)
        ->assertHeader('Content-Security-Policy');
})->with([
    'sign-in page' => ['/login', 200],
    'home, guest redirect' => ['/', 302],
    'unknown page' => ['/no-existe', 404],
    'API JSON' => ['/api/_test/json', 200],
    'unknown API route, JSON 404' => ['/api/no-existe', 404],
]);

it('sends no policy while the Vite dev server runs', function () {
    // The dev server serves the scripts and their hot updates from another
    // origin. A local run with built assets still gets the policy.
    $hotFile = storage_path('framework/testing/vite-running.hot');
    File::ensureDirectoryExists(dirname($hotFile));
    File::put($hotFile, 'http://localhost:5173');

    try {
        Vite::swap(coreCspVite($hotFile));

        $this->get('/_test/nonce')->assertHeaderMissing('Content-Security-Policy');
    } finally {
        File::delete($hotFile);
    }
});

it('puts the nonce on every inline script of every view', function () {
    $views = Finder::create()->files()->name('*.blade.php')->in([
        resource_path('views'),
        ...glob(app_path('Modules/*/resources/views'), GLOB_ONLYDIR) ?: [],
    ]);

    $missing = [];

    foreach ($views as $view) {
        preg_match_all('/<script\b(?![^>]*\bsrc=)[^>]*>/i', $view->getContents(), $tags);

        foreach ($tags[0] as $tag) {
            if (! str_contains($tag, 'nonce="{{ Vite::cspNonce() }}"')) {
                $missing[] = $view->getRelativePathname().': '.$tag;
            }
        }
    }

    expect($missing)->toBe([]);
});
