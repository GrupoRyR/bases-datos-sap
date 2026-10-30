<?php

namespace App\Modules\Panel\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;

/**
 * POST /panel/apps: the name of the new app, already trimmed by the web
 * middleware. Whether the name is taken is ClientAppKeys' call (revoked
 * apps count), so the controller turns its refusal into an error of this
 * same field. Errors go back to the list; the name is not personal data.
 */
final class StoreAppRequest extends FormRequest
{
    /** @var string */
    protected $redirectRoute = 'panel.apps';

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
            'nombre' => ['required', 'string', 'max:100'],
        ];
    }

    /**
     * @return array<string, string>
     */
    public function messages(): array
    {
        return [
            'nombre.max' => __('panel::apps.errores.nombre_largo'),
            'nombre.*' => __('panel::apps.errores.nombre'),
        ];
    }

    public function name(): string
    {
        return $this->string('nombre')->toString();
    }
}
