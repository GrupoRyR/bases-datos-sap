<?php

namespace App\Modules\Panel\Http\Controllers;

use App\Models\User;
use App\Modules\Core\Contracts\AuditLogger;
use App\Modules\Panel\Http\Requests\UpdateDataRequest;
use App\Modules\Panel\Support\Formats;
use App\Modules\Panel\Support\Labels;
use App\Modules\Panel\Support\UpdateOptions;
use App\Modules\Sap\Contracts\Data\UpdateRequestData;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\RequestState;
use App\Modules\Sap\Contracts\UpdateRequests;
use Illuminate\Contracts\View\View;
use Illuminate\Http\RedirectResponse;

/**
 * GET and POST /panel/actualizar (panel.actualizar, panel.actualizar.store),
 * only for core.administrar: TI's «Actualizar datos» button. It asks Sap
 * with the same rules as the apps (docs/contrato-robot.md, section 7.2):
 * it joins an identical waiting request or queues, and is never refused.
 * The options come from the Sap enums through UpdateOptions.
 */
final class UpdateDataController
{
    public function create(): View
    {
        return view('panel::actualizar', [
            'companies' => array_map(fn (Company $case): array => ['value' => $case->value, 'label' => Labels::company($case->value)], Company::cases()),
            'options' => array_map(fn (array $option): array => ['value' => $option['value'], 'label' => $option['label']], UpdateOptions::all()),
        ]);
    }

    public function store(UpdateDataRequest $request, UpdateRequests $updates, AuditLogger $audit): RedirectResponse
    {
        $user = $request->user();
        abort_unless($user instanceof User, 403);

        $company = $request->company();
        $dataset = $request->dataset();
        $scope = $request->scope();

        $result = $updates->request($company, $dataset, $scope, $user->email, $user->name);

        // Only the codes of what was asked: the user is on the entry itself.
        $audit->record('panel.request.placed', 'request', $result->id, [
            'empresa' => $company->value,
            'conjunto' => $dataset->value,
            'parte' => $scope?->value,
            'joined' => ! $result->created,
        ]);

        return redirect()->route('panel.actualizar')->with('status', $this->message($result));
    }

    /**
     * What happened, in the words of docs/guia-apps.md, section 2.4.
     */
    private function message(UpdateRequestData $result): string
    {
        $id = ['id' => $result->id];
        $runsAt = $result->state === RequestState::Queued && $result->runFrom !== null ? Formats::at($result->runFrom) : null;

        return match (true) {
            ! $result->created && $runsAt !== null => __('panel::actualizar.resultado.unida_hora', [...$id, 'cuando' => $runsAt]),
            ! $result->created => __('panel::actualizar.resultado.unida', $id),
            $runsAt !== null => __('panel::actualizar.resultado.en_cola_hora', [...$id, 'cuando' => $runsAt]),
            $result->state === RequestState::Queued => __('panel::actualizar.resultado.en_cola', $id),
            default => __('panel::actualizar.resultado.pendiente', $id),
        };
    }
}
