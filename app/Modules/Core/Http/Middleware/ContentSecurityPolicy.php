<?php

namespace App\Modules\Core\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Vite;
use Symfony\Component\HttpFoundation\Response;

/**
 * Sends the Content-Security-Policy of every response of the app (audit
 * S-04). CoreServiceProvider pushes it as global middleware, so redirects,
 * error pages and the API get it too. public/.htaccess sends the other
 * security headers; this one needs a nonce per request, so the app sends it.
 *
 * Each request gets a new nonce: Vite puts it on its script tags, and an
 * inline <script> must carry it with nonce="{{ Vite::cspNonce() }}".
 *
 * - script-src has no 'unsafe-eval': the app has no Alpine or other code
 *   that evaluates strings.
 * - style-src keeps 'unsafe-inline' without a nonce: the framework's error
 *   pages (404, 419, 500…) print their CSS in a <style> block, and a nonce
 *   would make the browser ignore 'unsafe-inline'.
 * - The Microsoft sign-in is a link and a redirect, not a form post, so
 *   form-action 'self' leaves it alone.
 *
 * There is no policy only while the Vite dev server runs (public/hot): it
 * serves the scripts and their hot updates from another origin. A local run
 * with built assets ("npm run build") gets the same policy as production, so
 * it can be checked before a deploy.
 */
final class ContentSecurityPolicy
{
    /**
     * @param  Closure(Request): Response  $next
     */
    public function handle(Request $request, Closure $next): Response
    {
        if (Vite::isRunningHot()) {
            return $next($request);
        }

        $nonce = Vite::useCspNonce();
        $response = $next($request);

        $response->headers->set('Content-Security-Policy', implode('; ', [
            "default-src 'self'",
            "script-src 'self' 'nonce-{$nonce}'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data:",
            "font-src 'self'",
            "connect-src 'self'",
            "manifest-src 'self'",
            "worker-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]));

        return $response;
    }
}
