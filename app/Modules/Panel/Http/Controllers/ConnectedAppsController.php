<?php

namespace App\Modules\Panel\Http\Controllers;

use App\Modules\Core\Contracts\AuditLogger;
use App\Modules\Panel\Http\Requests\StoreAppRequest;
use App\Modules\Panel\Support\Formats;
use App\Modules\Sap\Contracts\ClientAppKeys;
use App\Modules\Sap\Contracts\Data\ClientAppData;
use App\Modules\Sap\Contracts\Data\IssuedAppKey;
use Carbon\CarbonImmutable;
use Illuminate\Contracts\View\View;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Response;
use Illuminate\Validation\ValidationException;
use InvalidArgumentException;

/**
 * /panel/apps (panel.apps, panel.apps.store, panel.apps.rotate,
 * panel.apps.revoke), only for core.administrar: the apps that call /api/v1
 * and their keys (docs/contrato-robot.md, section 7.4). A new or rotated
 * key is shown once, on a page rendered straight from the POST: never
 * through a redirect, the session, the audit log or any log. Every change
 * is audited with the app's name and key prefix only.
 */
final class ConnectedAppsController
{
    public function index(ClientAppKeys $keys): View
    {
        return view('panel::apps', [
            'apps' => array_map($this->app(...), $keys->all()),
        ]);
    }

    public function store(StoreAppRequest $request, ClientAppKeys $keys, AuditLogger $audit): Response
    {
        try {
            $issued = $keys->issue($request->name());
        } catch (InvalidArgumentException) {
            // Validation already refused an empty name, so the name is taken.
            throw ValidationException::withMessages(['nombre' => __('panel::apps.errores.nombre_usado')])
                ->redirectTo(route('panel.apps'));
        }

        return $this->keyPage($issued, $keys, $audit, 'panel.app.created');
    }

    public function rotate(int $app, ClientAppKeys $keys, AuditLogger $audit): Response
    {
        try {
            $issued = $keys->rotate($app);
        } catch (InvalidArgumentException) {
            abort(404);
        }

        return $this->keyPage($issued, $keys, $audit, 'panel.app.key_rotated');
    }

    public function revoke(int $app, ClientAppKeys $keys, AuditLogger $audit): RedirectResponse
    {
        $found = $this->find($keys, $app) ?? abort(404);

        // Revoking twice changes nothing, so there is nothing to audit.
        if ($found->revokedAt === null) {
            $keys->revoke($found->id);
            $audit->record('panel.app.revoked', 'app', $found->id, ['nombre' => $found->name, 'prefijo' => $found->keyPrefix]);
        }

        return redirect()->route('panel.apps')->with('status', __('panel::apps.revocada', ['nombre' => $found->name]));
    }

    /**
     * Audits the new key by its prefix and shows it this once. no-store keeps
     * the page out of the browser cache and history.
     */
    private function keyPage(IssuedAppKey $issued, ClientAppKeys $keys, AuditLogger $audit, string $action): Response
    {
        $audit->record($action, 'app', $issued->id, [
            'nombre' => $issued->name,
            'prefijo' => $this->find($keys, $issued->id)?->keyPrefix,
        ]);

        return response()
            ->view('panel::apps-llave', ['name' => $issued->name, 'key' => $issued->key])
            ->header('Cache-Control', 'no-store, private');
    }

    private function find(ClientAppKeys $keys, int $id): ?ClientAppData
    {
        foreach ($keys->all() as $app) {
            if ($app->id === $id) {
                return $app;
            }
        }

        return null;
    }

    /**
     * One app as the view shows it, already in words.
     *
     * @return array<string, mixed>
     */
    private function app(ClientAppData $app): array
    {
        $moment = fn (CarbonImmutable $at): array => ['iso' => Formats::isoDateTime($at), 'text' => Formats::dateTime($at)];

        return [
            'id' => $app->id,
            'name' => $app->name,
            'keyPrefix' => $app->keyPrefix,
            'createdAt' => $moment($app->createdAt),
            'lastUsedAt' => $app->lastUsedAt === null ? null : $moment($app->lastUsedAt),
            'revokedAt' => $app->revokedAt === null ? null : $moment($app->revokedAt),
        ];
    }
}
