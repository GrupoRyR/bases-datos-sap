<?php

namespace App\Modules\Panel\Support;

use App\Modules\Sap\Contracts\Data\MasterRecordData;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Contracts\MasterLookup;
use Illuminate\Http\Response;
use Illuminate\Support\MessageBag;
use Illuminate\Support\ViewErrorBag;

/**
 * The lookup page (panel.consulta): the form, its errors and the records
 * found. The term can be a NIT or a name (Ley 1581), so the page is always
 * rendered from the request itself, never through the session, and every
 * response tells the browser not to store it.
 */
final class LookupPage
{
    /**
     * The parts MasterLookup can search, in form order. It mirrors the
     * contract, which refuses any other part.
     */
    public const array PARTS = [Part::Customers, Part::Suppliers, Part::Items];

    /**
     * The values the form may send as "parte".
     *
     * @return list<string>
     */
    public static function partValues(): array
    {
        return array_map(fn (Part $part): string => $part->value, self::PARTS);
    }

    /**
     * The page with the form filled with $values and, after a valid search,
     * the records found.
     *
     * @param  array{parte: string, empresa: string, termino: string}  $values
     * @param  list<MasterRecordData>|null  $records
     */
    public static function response(array $values, ?array $records = null, ?MessageBag $errors = null, int $status = 200): Response
    {
        return response()
            ->view('panel::consulta', [
                'values' => $values,
                'parts' => array_map(fn (Part $part): array => ['value' => $part->value, 'label' => Labels::part($part->value)], self::PARTS),
                'companies' => [
                    ['value' => '', 'label' => __('panel::consulta.las_dos')],
                    ...array_map(fn (Company $case): array => ['value' => $case->value, 'label' => Labels::company($case->value)], Company::cases()),
                ],
                'records' => $records === null ? null : array_map(self::record(...), $records),
                'capped' => $records !== null && count($records) >= MasterLookup::MAX_RESULTS,
                'errors' => (new ViewErrorBag)->put('default', $errors ?? new MessageBag),
            ], $status)
            ->header('Cache-Control', 'no-store, private');
    }

    /**
     * One record as the view shows it, already in words.
     *
     * @return array<string, mixed>
     */
    private static function record(MasterRecordData $record): array
    {
        return [
            'code' => $record->code,
            'name' => $record->name,
            'taxId' => filled($record->taxId) ? __('panel::consulta.registro.nit', ['nit' => $record->taxId]) : null,
            'company' => Labels::company($record->company->value),
            'active' => $record->active,
            'state' => __($record->active ? 'panel::consulta.registro.activo' : 'panel::consulta.registro.inactivo'),
            'updatedInSap' => $record->updatedInSap === null ? null : [
                'iso' => Formats::isoDateTime($record->updatedInSap),
                'text' => __('panel::consulta.registro.cambio', ['momento' => Formats::dateTime($record->updatedInSap)]),
            ],
            'syncedAt' => [
                'iso' => Formats::isoDateTime($record->syncedAt),
                'text' => __('panel::consulta.registro.llego', ['momento' => Formats::dateTime($record->syncedAt)]),
            ],
        ];
    }
}
