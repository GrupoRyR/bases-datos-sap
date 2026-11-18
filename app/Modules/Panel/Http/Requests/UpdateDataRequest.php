<?php

namespace App\Modules\Panel\Http\Requests;

use App\Modules\Panel\Support\Labels;
use App\Modules\Panel\Support\UpdateOptions;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\RequestScope;
use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rule;
use Illuminate\Validation\Validator;

/**
 * POST /panel/actualizar: the company and what to update ("MAESTROS" or
 * "MAESTROS:clientes"). Both must be one of the form's options, built
 * from the Sap enums, so a scope that does not belong to its dataset never
 * reaches the contract, and the dataset must exist for the company
 * (PRODUCCION is Segurex only). The route already asks for core.administrar.
 */
final class UpdateDataRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }

    /**
     * @return array<string, mixed>
     */
    public function rules(): array
    {
        return [
            'empresa' => ['required', 'string', Rule::enum(Company::class)],
            'datos' => ['required', 'string', Rule::in(UpdateOptions::values())],
        ];
    }

    /**
     * A dataset some company does not have (Dataset::companies) is refused
     * for that company, before Sap would refuse it.
     *
     * @return list<callable(Validator): void>
     */
    public function after(): array
    {
        return [function (Validator $validator): void {
            if ($validator->errors()->isNotEmpty()) {
                return;
            }

            $dataset = $this->dataset();

            if (! in_array($this->company(), $dataset->companies(), true)) {
                $validator->errors()->add('datos', __('panel::actualizar.errores.empresa_conjunto', [
                    'conjunto' => Labels::dataset($dataset->value),
                    'empresas' => implode(', ', array_map(fn (Company $company): string => Labels::company($company->value), $dataset->companies())),
                ]));
            }
        }];
    }

    /**
     * @return array<string, string>
     */
    public function messages(): array
    {
        return [
            'empresa.*' => __('panel::actualizar.errores.empresa'),
            'datos.*' => __('panel::actualizar.errores.datos'),
        ];
    }

    public function company(): Company
    {
        return Company::from($this->string('empresa')->toString());
    }

    public function dataset(): Dataset
    {
        return $this->option()['dataset'];
    }

    public function scope(): ?RequestScope
    {
        return $this->option()['scope'];
    }

    /**
     * @return array{dataset: Dataset, scope: RequestScope|null}
     */
    private function option(): array
    {
        // Validation already checked the value against the same options.
        return UpdateOptions::find($this->string('datos')->toString())
            ?? throw new \LogicException('The update option was not validated.');
    }
}
