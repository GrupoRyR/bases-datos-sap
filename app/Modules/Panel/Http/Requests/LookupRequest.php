<?php

namespace App\Modules\Panel\Http\Requests;

use App\Modules\Panel\Support\LookupPage;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Part;
use Illuminate\Contracts\Validation\Validator;
use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Http\Exceptions\HttpResponseException;
use Illuminate\Validation\Rule;

/**
 * POST /panel/consulta: what to look up (one of LookupPage::PARTS), the
 * company (empty for both) and the term, already trimmed by the web
 * middleware. An invalid search shows the form again straight from this
 * request with a 422: the usual redirect would flash the term, which can be
 * a NIT or a name, into the session.
 */
final class LookupRequest extends FormRequest
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
            'parte' => ['required', 'string', Rule::in(LookupPage::partValues())],
            'empresa' => ['nullable', 'string', Rule::enum(Company::class)],
            'termino' => ['required', 'string', 'min:2', 'max:100'],
        ];
    }

    /**
     * @return array<string, string>
     */
    public function messages(): array
    {
        return [
            'parte.*' => __('panel::consulta.errores.parte'),
            'empresa.*' => __('panel::consulta.errores.empresa'),
            'termino.min' => __('panel::consulta.errores.termino_corto'),
            'termino.max' => __('panel::consulta.errores.termino_largo'),
            'termino.*' => __('panel::consulta.errores.termino'),
        ];
    }

    public function part(): Part
    {
        return Part::from($this->text('parte'));
    }

    public function company(): ?Company
    {
        return Company::tryFrom($this->text('empresa'));
    }

    public function term(): string
    {
        return $this->text('termino');
    }

    /**
     * What the form sent, to fill it again.
     *
     * @return array{parte: string, empresa: string, termino: string}
     */
    public function values(): array
    {
        return [
            'parte' => $this->text('parte'),
            'empresa' => $this->text('empresa'),
            'termino' => $this->text('termino'),
        ];
    }

    protected function failedValidation(Validator $validator): never
    {
        throw new HttpResponseException(LookupPage::response($this->values(), errors: $validator->errors(), status: 422));
    }

    /**
     * A field as text; anything that is not a string (say an array) is empty.
     */
    private function text(string $key): string
    {
        $value = $this->input($key);

        return is_string($value) ? $value : '';
    }
}
