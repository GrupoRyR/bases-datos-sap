<?php

use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\Part;
use Illuminate\Database\QueryException;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/*
| The tables and v_* views of MAESTROS (maestros_sap) and CARTERA
| (cartera_sap): docs/plan-bases-sap.md, section 4, and docs/arquitectura.md, section 4.
*/

/** @return list<string> */
function sortedColumns(string $connection, string $table): array
{
    $columns = Schema::connection($connection)->getColumnListing($table);
    sort($columns);

    return $columns;
}

/**
 * What a view exposes: the company, the columns of the contract, the flags
 * every master row carries and the sync time. Never the internal id or run.
 *
 * @return list<string>
 */
function expectedViewColumns(Part $part): array
{
    $columns = ['empresa', ...array_keys($part->columns()), 'sincronizado_en'];

    if ($part->dataset() === Dataset::Maestros) {
        $columns = [...$columns, 'activo', 'actualizado_en_sap'];
    }

    $columns = array_values(array_unique($columns));
    sort($columns);

    return $columns;
}

/**
 * A valid row for the part, with invented values for the required columns.
 *
 * @return array<string, mixed>
 */
function inventedRow(Part $part, string $company, int|string $key = 'K1'): array
{
    $row = ['empresa' => $company, 'sincronizado_en' => '2026-10-26 02:30:00'];

    foreach ($part->columns() as $name => $column) {
        if (! $column->required) {
            continue;
        }

        $row[$name] = match ($column->type->value) {
            'integer' => is_int($key) ? $key : 1,
            'decimal' => '10.50',
            'boolean' => true,
            'date' => '2026-10-25',
            'datetime' => '2026-10-25 09:15:02',
            default => is_string($key) ? $key : 'K1',
        };
    }

    return $row;
}

it('creates the table of every part on the connection of its dataset', function (Part $part) {
    $connection = $part->dataset()->connection();
    $columns = sortedColumns($connection, $part->table());

    foreach (['id', 'empresa', 'sincronizado_en', 'corrida_id', ...array_keys($part->columns())] as $column) {
        expect($columns)->toContain($column);
    }

    if ($part->dataset() === Dataset::Maestros) {
        expect($columns)->toContain('activo')->toContain('actualizado_en_sap');
    }
})->with(Part::cases());

it('exposes every part through a stable view without internal columns', function (Part $part) {
    expect(sortedColumns($part->dataset()->connection(), $part->view()))->toBe(expectedViewColumns($part));
})->with(Part::cases());

it('keeps one row per company and key in every master table', function (Part $part) {
    $table = DB::connection('maestros')->table($part->table());
    $key = $part->columns()[$part->key()[0]]->type->value === 'integer' ? 7 : 'K7';

    $table->insert(inventedRow($part, 'SGX', $key));
    // The same key in the other company is another row.
    $table->insert(inventedRow($part, 'SDC', $key));

    expect(fn () => $table->insert(inventedRow($part, 'SGX', $key)))->toThrow(QueryException::class);
})->with(Part::forDataset(Dataset::Maestros));

it('reads a master row through its view', function () {
    DB::connection('maestros')->table('clientes')->insert([
        ...inventedRow(Part::Customers, 'SGX', 'C800123456'),
        'nombre' => 'Ferretería La Llave SAS',
        'corrida_id' => 42,
    ]);

    $row = (array) DB::connection('maestros')->table('v_clientes')->sole();

    expect($row['codigo'])->toBe('C800123456')
        ->and($row['nombre'])->toBe('Ferretería La Llave SAS')
        ->and($row['empresa'])->toBe('SGX')
        ->and((bool) $row['activo'])->toBeTrue()
        ->and($row)->not->toHaveKeys(['id', 'corrida_id']);
});

it('keeps many receivable lines of the same document, since CARTERA has no natural key', function () {
    $line = inventedRow(Part::Receivables, 'SGX', 'FV-1001');

    DB::connection('cartera')->table('cartera')->insert([$line, $line]);

    expect(DB::connection('cartera')->table('v_cartera')->count())->toBe(2);
});

it('stores the daily photo of CARTERA by cut-off date and exposes it in a view', function () {
    DB::connection('cartera')->table('cartera_fotos')->insert([
        ...inventedRow(Part::Receivables, 'SDC', 'FV-2002'),
        'fecha_corte' => '2026-10-25',
    ]);

    $columns = sortedColumns('cartera', 'v_cartera_fotos');
    $row = (array) DB::connection('cartera')->table('v_cartera_fotos')->sole();

    expect($columns)->toBe(collect([...expectedViewColumns(Part::Receivables), 'fecha_corte'])->sort()->values()->all())
        ->and($row['fecha_corte'])->toStartWith('2026-10-25')
        ->and($row['empresa'])->toBe('SDC');
});
