<?php

use App\Modules\Sap\Contracts\Data\MasterRecordData;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Contracts\MasterLookup;
use Illuminate\Support\Facades\DB;

/*
| The lookup of customers, suppliers and items through Contracts\MasterLookup:
| only identifying fields (Ley 1581), a hard limit and safe LIKE matching.
*/

/** @param  array<string, mixed>  $row */
function lookupRow(string $table, array $row): void
{
    DB::connection('maestros')->table($table)->insert(array_merge([
        'empresa' => 'SGX', 'activo' => true, 'sincronizado_en' => '2026-10-27 02:30:00',
    ], $row));
}

/**
 * @param  list<MasterRecordData>  $records
 * @return list<string>
 */
function lookupCodes(array $records): array
{
    return array_map(fn (MasterRecordData $record): string => $record->company->value.':'.$record->code, $records);
}

beforeEach(function () {
    lookupRow('clientes', ['codigo' => 'C100', 'nombre' => 'Ferretería Andina', 'nit' => '900123', 'actualizado_en_sap' => '2026-10-20 08:15:00']);
    lookupRow('clientes', ['empresa' => 'SDC', 'codigo' => 'C200', 'nombre' => 'Andamios del Sur', 'nit' => '800555', 'activo' => false]);
    lookupRow('clientes', ['codigo' => 'AC2', 'nombre' => 'Beta', 'nit' => '19001']);
    lookupRow('clientes', ['codigo' => 'P1', 'nombre' => 'Otra 50% SA']);
    lookupRow('clientes', ['codigo' => 'P2', 'nombre' => 'Otra 500 SA']);
    lookupRow('clientes', ['codigo' => 'P3', 'nombre' => 'Otra 5_0 SA']);
});

it('matches a code or tax id that starts with the term, or a name that contains it, ignoring case', function () {
    $lookup = app(MasterLookup::class);

    expect(lookupCodes($lookup->search(Part::Customers, 'c2')))->toBe(['SDC:C200'])
        ->and(lookupCodes($lookup->search(Part::Customers, '9001')))->toBe(['SGX:C100'])
        ->and(lookupCodes($lookup->search(Part::Customers, ' ANDI ')))->toBe(['SGX:C100'])
        ->and(lookupCodes($lookup->search(Part::Customers, 'and')))->toBe(['SDC:C200', 'SGX:C100'])
        ->and(lookupCodes($lookup->search(Part::Customers, 'and', Company::Sgx)))->toBe(['SGX:C100'])
        ->and(lookupCodes($lookup->search(Part::Suppliers, 'and')))->toBe([]);
});

it('returns the identifying fields of each row', function () {
    [$record] = app(MasterLookup::class)->search(Part::Customers, 'C100');

    expect($record->company)->toBe(Company::Sgx)
        ->and($record->part)->toBe(Part::Customers)
        ->and($record->name)->toBe('Ferretería Andina')
        ->and($record->taxId)->toBe('900123')
        ->and($record->active)->toBeTrue()
        ->and($record->updatedInSap?->format('Y-m-d H:i'))->toBe('2026-10-20 08:15')
        ->and($record->syncedAt->format('Y-m-d H:i'))->toBe('2026-10-27 02:30')
        ->and(app(MasterLookup::class)->search(Part::Customers, 'C200')[0]->active)->toBeFalse();
});

it('selects only the identifying columns of the view', function () {
    lookupRow('articulos', ['codigo' => 'A1', 'nombre' => 'Tornillo']);
    DB::connection('maestros')->enableQueryLog();

    app(MasterLookup::class)->search(Part::Customers, 'beta');
    $items = app(MasterLookup::class)->search(Part::Items, 'torn');

    $queries = array_map(fn (array $query): string => str_replace(['"', '`'], '', $query['query']), DB::connection('maestros')->getQueryLog());

    expect($queries[0])->toStartWith('select empresa, codigo, nombre, nit, activo, actualizado_en_sap, sincronizado_en from v_clientes ')
        ->and($queries[1])->toStartWith('select empresa, codigo, nombre, activo, actualizado_en_sap, sincronizado_en from v_articulos ')
        ->and($items[0]->taxId)->toBeNull();
});

it('treats LIKE wildcards in the term as plain characters', function () {
    $lookup = app(MasterLookup::class);

    expect(lookupCodes($lookup->search(Part::Customers, '50%')))->toBe(['SGX:P1'])
        ->and(lookupCodes($lookup->search(Part::Customers, '5_0')))->toBe(['SGX:P3'])
        ->and($lookup->search(Part::Customers, 'a!b'))->toBe([]);
});

it('orders by name, company and code and clamps the limit', function () {
    foreach (range(1, 30) as $number) {
        lookupRow('articulos', ['empresa' => $number % 2 === 0 ? 'SGX' : 'SDC', 'codigo' => sprintf('T%02d', $number), 'nombre' => 'Tornillo']);
    }
    $lookup = app(MasterLookup::class);

    expect($lookup->search(Part::Items, 'tornillo', limit: 100))->toHaveCount(MasterLookup::MAX_RESULTS)
        ->and(lookupCodes($lookup->search(Part::Items, 'tornillo', limit: 0)))->toBe(['SDC:T01'])
        ->and(lookupCodes($lookup->search(Part::Items, 'tornillo', limit: 3)))->toBe(['SDC:T01', 'SDC:T03', 'SDC:T05']);
});

it('refuses other parts and terms shorter than 2 characters', function (Part $part, string $term) {
    app(MasterLookup::class)->search($part, $term);
})->throws(InvalidArgumentException::class)->with([
    'contacts' => [Part::Contacts, 'ana'],
    'receivables' => [Part::Receivables, 'ana'],
    'prices' => [Part::Prices, 'ana'],
    'one character' => [Part::Customers, ' a '],
    'empty' => [Part::Customers, ''],
]);
