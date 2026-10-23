<?php

namespace App\Modules\Core\Http\Controllers\Auth;

use Illuminate\Contracts\View\View;

/**
 * GET /login (core.login, guests only): the sign-in page, with one button
 * that goes to Microsoft and the flashed status or error.
 */
final class LoginController
{
    public function __invoke(): View
    {
        return view('core::auth.login');
    }
}
