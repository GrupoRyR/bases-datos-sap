<?php

namespace App\Modules\Sap\Application\Panel;

use App\Modules\Sap\Contracts\Data\MasterRecordData;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Contracts\MasterLookup;
use Carbon\CarbonImmutable;
use Illuminate\Database\Query\Builder;
use Illuminate\Support\Facades\DB;
use InvalidArgumentException;
use stdClass;

/**
 * Searches the stable view of the part on its dataset connection. Matching
 * lowers both sides and uses LIKE with "!" as escape character, which
 * SQLite and MySQL read the same way.
 */
final class DatabaseMasterLookup implements MasterLookup
{
    /** The only parts TI may look up. */
    private const PARTS = [Part::Customers, Part::Suppliers, Part::Items];

    public function search(Part $part, string $term, ?Company $company = null, int $limit = 10): array
    {
        $term = mb_strtolower(trim($term));

        if (! in_array($part, self::PARTS, true) || mb_strlen($term) < 2) {
            throw new InvalidArgumentException('Busca clientes, proveedores o artículos con al menos 2 caracteres.');
        }

        $hasTaxId = isset($part->columns()['nit']);
        $escaped = str_replace(['!', '%', '_'], ['!!', '!%', '!_'], $term);
        // Only identifying fields (Ley 1581): never phones, e-mails or addresses.
        $columns = ['empresa', 'codigo', 'nombre', ...($hasTaxId ? ['nit'] : []), 'activo', 'actualizado_en_sap', 'sincronizado_en'];

        $rows = DB::connection($part->dataset()->connection())->table($part->view())
            ->select($columns)
            ->when($company, fn (Builder $query, Company $company) => $query->where('empresa', $company->value))
            ->where(function (Builder $query) use ($escaped, $hasTaxId) {
                $query->whereRaw("LOWER(codigo) LIKE ? ESCAPE '!'", ["{$escaped}%"])
                    ->orWhereRaw("LOWER(nombre) LIKE ? ESCAPE '!'", ["%{$escaped}%"])
                    ->when($hasTaxId, fn (Builder $query) => $query->orWhereRaw("LOWER(nit) LIKE ? ESCAPE '!'", ["{$escaped}%"]));
            })
            ->orderBy('nombre')
            ->orderBy('empresa')
            ->orderBy('codigo')
            ->limit(min(max(1, $limit), self::MAX_RESULTS))
            ->get();

        $timezone = (string) config('app.timezone');

        return $rows->map(fn (stdClass $row): MasterRecordData => new MasterRecordData(
            company: Company::from($row->empresa),
            part: $part,
            code: (string) $row->codigo,
            name: (string) $row->nombre,
            taxId: $hasTaxId ? $row->nit : null,
            active: (bool) $row->activo,
            updatedInSap: $row->actualizado_en_sap === null ? null : CarbonImmutable::parse((string) $row->actualizado_en_sap, $timezone),
            syncedAt: CarbonImmutable::parse((string) $row->sincronizado_en, $timezone),
        ))->values()->all();
    }
}
