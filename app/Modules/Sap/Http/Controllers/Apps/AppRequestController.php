<?php

namespace App\Modules\Sap\Http\Controllers\Apps;

use App\Modules\Sap\Application\Requests\PlaceRequest;
use App\Modules\Sap\Contracts\Data\UpdateRequestData;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\RequestScope;
use App\Modules\Sap\Http\Exceptions\RobotRequestRejected;
use App\Modules\Sap\Models\ClientApp;
use App\Modules\Sap\Models\UpdateRequest;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

/**
 * POST /api/v1/solicitudes and GET /api/v1/solicitudes/{id}
 * (docs/contrato-robot.md, section 7.4). The app is the one of the key;
 * solicitado_por is the person, and both are recorded.
 */
final class AppRequestController
{
    public function store(Request $request, PlaceRequest $requests): JsonResponse
    {
        $errors = [];
        $company = Company::tryFrom($this->text($request->input('empresa')));
        $dataset = Dataset::tryFrom($this->text($request->input('conjunto')));
        $scope = $request->input('parte') === null ? null : RequestScope::tryFrom($this->text($request->input('parte')));
        $email = $this->text($request->input('solicitado_por.correo'));
        $name = $request->input('solicitado_por.nombre');

        if ($company === null) {
            $errors['empresa'] = 'Empresa desconocida: solo SGX o SDC.';
        }

        if ($dataset === null) {
            $errors['conjunto'] = 'Conjunto desconocido: solo MAESTROS, CARTERA o VENTAS.';
        } elseif ($request->input('parte') !== null && ($scope === null || ! in_array($scope, RequestScope::forDataset($dataset), true))) {
            $errors['parte'] = match ($dataset) {
                Dataset::Maestros => 'Parte desconocida: clientes, proveedores, articulos, precios, vendedores o catalogos.',
                Dataset::Cartera => 'CARTERA se pide completa: parte debe ser null.',
                Dataset::Ventas => 'VENTAS se pide completo: parte debe ser null.',
            };
        }

        if (filter_var($email, FILTER_VALIDATE_EMAIL) === false) {
            $errors['solicitado_por.correo'] = 'Debe ser el correo de quien pidió.';
        }

        if ($name !== null && (! is_string($name) || mb_strlen($name) > 255)) {
            $errors['solicitado_por.nombre'] = 'Debe ser texto de hasta 255 caracteres.';
        }

        if ($errors !== [] || $dataset === null) {
            throw RobotRequestRejected::invalid('La solicitud no cumple el contrato.', $errors);
        }

        $placed = $requests->place($company, $dataset, $scope, $email, $name, $this->app($request)->id);

        return response()->json($this->summary($placed), $placed->created ? 201 : 200);
    }

    public function show(Request $request, int $id): JsonResponse
    {
        $found = UpdateRequest::query()
            ->whereKey($id)
            ->whereExists(fn ($query) => $query->from('update_request_requesters')
                ->whereColumn('update_request_requesters.update_request_id', 'update_requests.id')
                ->where('update_request_requesters.client_app_id', $this->app($request)->id))
            ->first() ?? throw new RobotRequestRejected(404, 'La solicitud no existe.');

        $data = $found->toData();

        return response()->json([
            ...$this->summary($data),
            'tomada_en' => $data->takenAt?->toIso8601String(),
            'terminada_en' => $data->finishedAt?->toIso8601String(),
            'error' => $data->error,
            'solicitada_en' => $data->requestedAt->toIso8601String(),
        ]);
    }

    /**
     * @return array<string, mixed>
     */
    private function summary(UpdateRequestData $request): array
    {
        return [
            'id' => $request->id,
            'estado' => $request->state->value,
            'correr_desde' => $request->runFrom?->toIso8601String(),
            'empresa' => $request->company->value,
            'conjunto' => $request->dataset->value,
            'parte' => $request->scope?->value,
        ];
    }

    private function app(Request $request): ClientApp
    {
        /** @var ClientApp */
        return $request->attributes->get('client_app');
    }

    private function text(mixed $value): string
    {
        return is_string($value) ? trim($value) : '';
    }
}
