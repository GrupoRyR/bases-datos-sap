<?php

namespace App\Modules\Core\Http\Controllers;

use App\Models\User;
use Illuminate\Contracts\View\View;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Gate;

/**
 * GET /sin-acceso (core.sin-acceso, signed-in users only): tells a user
 * without a role to ask TI for one. A user who has access goes home.
 */
final class NoAccessController
{
    public function __invoke(Request $request): View|RedirectResponse
    {
        $user = $request->user();

        if ($user instanceof User && Gate::forUser($user)->allows('core.consultar')) {
            return redirect()->route('core.inicio');
        }

        return view('core::sin-acceso', ['user' => $user]);
    }
}
