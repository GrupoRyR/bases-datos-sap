<?php

namespace App\Modules\Sap\Http\Controllers\Apps;

use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Domain\Runs\RunState;
use App\Modules\Sap\Http\Exceptions\RobotRequestRejected;
use App\Modules\Sap\Models\Run;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

/**
 * GET /api/v1/estado?empresa=SGX&conjunto=CARTERA (docs/contrato-robot.md,
 * section 7.4): per part, the last time a run applied it, so an app can
 * show "Datos actualizados a las 10:42".
 */
final class StatusController
{
    public function __invoke(Request $request): JsonResponse
    {
        $company = Company::tryFrom((string) $request->query('empresa'));
        $dataset = Dataset::tryFrom((string) $request->query('conjunto'));

        if ($company === null || $dataset === null) {
            throw RobotRequestRejected::invalid('La consulta no cumple el contrato.', array_filter([
                'empresa' => $company === null ? 'Empresa desconocida: solo SGX o SDC.' : null,
                'conjunto' => $dataset === null ? 'Conjunto desconocido: solo MAESTROS o CARTERA.' : null,
            ]));
        }

        $updated = array_fill_keys(array_map(fn (Part $part): string => $part->value, Part::forDataset($dataset)), null);
        $missing = count($updated);

        // Newest closed runs first, until every part has its time.
        foreach (Run::where('conjunto', $dataset)->where('empresa', $company)->where('estado', RunState::Closed)
            ->orderByDesc('aplicada_en')->cursor() as $run) {
            foreach (array_keys($run->partes) as $part) {
                if (array_key_exists($part, $updated) && $updated[$part] === null && $run->aplicada_en !== null) {
                    $updated[$part] = $run->aplicada_en->toIso8601String();
                    $missing--;
                }
            }

            if ($missing === 0) {
                break;
            }
        }

        return response()->json([
            'empresa' => $company->value,
            'conjunto' => $dataset->value,
            'partes' => array_map(fn (?string $time): array => ['actualizado_en' => $time], $updated),
        ]);
    }
}
