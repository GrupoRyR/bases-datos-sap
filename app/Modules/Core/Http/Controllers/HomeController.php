<?php

namespace App\Modules\Core\Http\Controllers;

use App\Models\User;
use Illuminate\Contracts\View\View;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Gate;

/**
 * GET / (core.inicio, signed-in users only): the home of the TI panel. A
 * user without a role (no core.consultar) goes to the page that asks for
 * access instead.
 */
final class HomeController
{
    public function __invoke(Request $request): View|RedirectResponse
    {
        $user = $request->user();

        if (! $user instanceof User || Gate::forUser($user)->denies('core.consultar')) {
            return redirect()->route('core.sin-acceso');
        }

        return view('core::inicio', ['user' => $user]);
    }
}
