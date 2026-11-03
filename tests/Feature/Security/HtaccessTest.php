<?php

use Illuminate\Support\Facades\File;

/*
| public/.htaccess forces https and sends the security headers on the GoDaddy
| Apache (audit S-03 and S-04). "php artisan serve" ignores it and no test
| runs Apache, so these checks only read the file: they keep anyone from
| dropping a rule without noticing.
*/

function htaccess(): string
{
    return str_replace("\r\n", "\n", File::get(public_path('.htaccess')));
}

it('sends plain http to https, except behind a TLS proxy and for .well-known', function () {
    expect(htaccess())
        ->toContain('RewriteCond %{HTTPS} !=on')
        ->toContain('RewriteCond %{HTTP:X-Forwarded-Proto} !=https')
        ->toContain('RewriteCond %{REQUEST_URI} !^/\.well-known/')
        ->toContain('RewriteRule ^ https://%{HTTP_HOST}%{REQUEST_URI} [L,R=301]');
});

it('redirects to https before any other rewrite', function () {
    $contents = htaccess();

    expect(strpos($contents, 'RewriteRule ^ https://'))
        ->toBeLessThan(strpos($contents, 'RewriteRule (^|/)\.(?!well-known/) - [F,L]'))
        ->toBeLessThan(strpos($contents, 'RewriteRule ^ index.php [L]'));
});

it('lists no directories and serves no dotfiles', function () {
    expect(htaccess())
        ->toStartWith("# No directory listings, with or without mod_negotiation.\nOptions -Indexes\n")
        ->toContain('RewriteRule (^|/)\.(?!well-known/) - [F,L]');
});

it('sends the security headers on every response', function (string $header) {
    expect(htaccess())->toContain($header);
})->with([
    'HSTS over https only, without subdomains' => 'Header always set Strict-Transport-Security "max-age=31536000" env=HTTPS',
    'no MIME sniffing' => 'Header always set X-Content-Type-Options "nosniff"',
    'no framing' => 'Header always set X-Frame-Options "DENY"',
    'referrer' => 'Header always set Referrer-Policy "strict-origin-when-cross-origin"',
    'permissions' => 'Header always set Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=(), usb=()"',
    'no PHP version on errors' => 'Header always unset X-Powered-By',
    'no PHP version on pages' => 'Header unset X-Powered-By',
]);

it('keeps HSTS off other subdomains of the company', function () {
    expect(htaccess())->not->toMatch('/^\s*Header\b.*includeSubDomains/mi');
});
