<?php

use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\Part;
use Illuminate\Database\QueryException;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/*
| The tables and v_* views of MAESTROS (maestros_sap), CARTERA (cartera_sap),
| VENTAS, PEDIDOS and PRODUCCION (all in ventas_sap): docs/plan-bases-sap.md, section 4,
| docs/arquitectura.md, section 4, and docs/contrato-robot.md, sections 11 and 12.
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

    if ($part === Part::Receivables) {
        // The day the overdue days are counted to (contract section 6).
        $columns[] = 'fecha_corte';
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
            'quantity' => '2.500000',
            'boolean' => true,
            'date' => '2026-10-25',
            'datetime' => '2026-10-25 09:15:02',
            // MySQL rejects a value longer than the column (direcciones.tipo is 1).
            default => mb_substr(is_string($key) ? $key : 'K1', 0, $column->length ?? 255),
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

it('treats SAP keys that differ only in case as different rows', function () {
    $addresses = DB::connection('maestros')->table('direcciones');
    $address = fn (string $partner, string $name): array => [
        ...inventedRow(Part::Addresses, 'SGX'),
        'codigo_socio' => $partner,
        'tipo' => 'S',
        'nombre' => $name,
    ];

    $addresses->insert([$address('C001', 'Bodega'), $address('C001', 'BODEGA'), $address('c001', 'Bodega')]);

    expect($addresses->count())->toBe(3);
})->skip(fn () => DB::connection('maestros')->getDriverName() !== 'mysql', 'SQLite compares text with BINARY already; MySQL is checked in CI.');

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

    expect($columns)->toBe(expectedViewColumns(Part::Receivables))
        ->and($row['fecha_corte'])->toStartWith('2026-10-25')
        ->and($row['empresa'])->toBe('SDC');
});

it('keeps one VENTAS line per company, document type, document and line', function () {
    $sales = DB::connection('ventas')->table('ventas');
    $line = fn (string $company, int $type, int $entry, int $line): array => [
        ...inventedRow(Part::Sales, $company), 'tipo_objeto' => $type, 'doc_entry' => $entry, 'linea' => $line,
    ];

    // An invoice and a credit note may share DocEntry; the other company too.
    $sales->insert([$line('SGX', 13, 500, 0), $line('SGX', 13, 500, 1), $line('SGX', 14, 500, 0), $line('SDC', 13, 500, 0)]);

    expect($sales->count())->toBe(4)
        ->and(fn () => $sales->insert($line('SGX', 13, 500, 1)))->toThrow(QueryException::class);
});

it('stores VENTAS quantities and rates with 6 decimals and reads them through v_ventas', function () {
    DB::connection('ventas')->table('ventas')->insert([
        ...inventedRow(Part::Sales, 'SGX'),
        'cantidad' => '-2.123456',
        'trm' => '4123.456789',
        'total' => '-2380.55',
        'corrida_id' => 42,
    ]);

    $row = (array) DB::connection('ventas')->table('v_ventas')->sole();

    expect((float) $row['cantidad'])->toBe(-2.123456)
        ->and((string) $row['trm'])->toStartWith('4123.456789')
        ->and((float) $row['total'])->toBe(-2380.55)
        ->and($row['empresa'])->toBe('SGX')
        ->and($row)->not->toHaveKeys(['id', 'corrida_id']);
});

it('exposes the gross profit through v_ventas, nullable and with its sign', function () {
    $sales = DB::connection('ventas')->table('ventas');
    $line = fn (int $entry, array $overrides): array => [
        ...inventedRow(Part::Sales, 'SGX'), 'doc_entry' => $entry, ...$overrides,
    ];

    $sales->insert([
        $line(1, ['ganancia_bruta' => '1234567.89']),
        $line(2, ['tipo_objeto' => 14, 'ganancia_bruta' => '-100.50']),
        $line(3, ['ganancia_bruta' => null]),
    ]);

    $profit = DB::connection('ventas')->table('v_ventas')->orderBy('doc_entry')->pluck('ganancia_bruta', 'doc_entry')
        ->map(fn (mixed $value): ?float => $value === null ? null : (float) $value)->all();

    expect($profit)->toBe([1 => 1234567.89, 2 => -100.5, 3 => null])
        ->and(Schema::connection('ventas')->getColumnListing('v_ventas'))->toContain('ganancia_bruta');
});

it('keeps one PEDIDOS line per company, order and line', function () {
    $orders = DB::connection('ventas')->table('pedidos');
    $line = fn (string $company, int $entry, int $line): array => [
        ...inventedRow(Part::Orders, $company), 'doc_entry' => $entry, 'linea' => $line,
    ];

    $orders->insert([$line('SGX', 3859, 0), $line('SGX', 3859, 1), $line('SDC', 3859, 0)]);

    expect($orders->count())->toBe(3)
        ->and(fn () => $orders->insert($line('SGX', 3859, 1)))->toThrow(QueryException::class);
});

it('stores PEDIDOS quantities and rates with 6 decimals and reads them through v_pedidos', function () {
    DB::connection('ventas')->table('pedidos')->insert([
        ...inventedRow(Part::Orders, 'SDC'),
        'dias_atraso' => -12,
        'cantidad_pendiente' => '400.000000',
        'descuento_documento' => '12.345678',
        'trm' => '4123.456789',
        'total_pendiente' => '1234567.89',
        'ganancia_bruta_pendiente' => '-100.50',
        'corrida_id' => 42,
    ]);

    $row = (array) DB::connection('ventas')->table('v_pedidos')->sole();

    expect((float) $row['cantidad_pendiente'])->toBe(400.0)
        ->and((string) $row['descuento_documento'])->toStartWith('12.345678')
        ->and((string) $row['trm'])->toStartWith('4123.456789')
        ->and((float) $row['total_pendiente'])->toBe(1234567.89)
        ->and((float) $row['ganancia_bruta_pendiente'])->toBe(-100.5)
        ->and((int) $row['dias_atraso'])->toBe(-12)
        ->and($row['empresa'])->toBe('SDC')
        ->and($row)->not->toHaveKeys(['id', 'corrida_id']);
});

it('keeps one PRODUCCION row per company and key in the keyed parts', function (Part $part, array $key) {
    $table = DB::connection('ventas')->table($part->table());
    $row = fn (string $company): array => [...inventedRow($part, $company), ...$key];

    $table->insert([$row('SGX'), $row('SDC')]);

    expect(fn () => $table->insert($row('SGX')))->toThrow(QueryException::class);
})->with([
    'produccion_terminado' => [Part::ProductionFinished, ['doc_entry' => 81, 'linea' => 2]],
    'produccion_costeo_teorico' => [Part::StandardCosts, ['codigo_articulo' => 'PT-100']],
]);

it('keeps repeated rows in the PRODUCCION parts without a key', function (Part $part) {
    $table = DB::connection('ventas')->table($part->table());

    $table->insert([inventedRow($part, 'SGX'), inventedRow($part, 'SGX')]);

    expect($table->count())->toBe(2);
})->with([Part::PlantLoad, Part::ProductionCosts, Part::BillOfMaterials, Part::Routings]);

it('stores PRODUCCION quantities with 6 decimals and amounts with 2, and reads them through the views', function () {
    DB::connection('ventas')->table('produccion_carga_planta')->insert([
        ...inventedRow(Part::PlantLoad, 'SGX'),
        'unidades' => '1250.000000',
        'horas' => '3.416667',
        'corrida_id' => 42,
    ]);
    DB::connection('ventas')->table('produccion_costos')->insert([
        ...inventedRow(Part::ProductionCosts, 'SGX'),
        'costo' => '-1525367102.33',
    ]);

    $load = (array) DB::connection('ventas')->table('v_produccion_carga_planta')->sole();
    $cost = (array) DB::connection('ventas')->table('v_produccion_costos')->sole();

    expect((float) $load['unidades'])->toBe(1250.0)
        ->and((string) $load['horas'])->toStartWith('3.416667')
        ->and($load['empresa'])->toBe('SGX')
        ->and($load)->not->toHaveKeys(['id', 'corrida_id'])
        ->and((float) $cost['costo'])->toBe(-1525367102.33);
});

it('adds contacto_principal and telefono_2 at the end of their views, after every older column', function (string $view, string $column) {
    $columns = Schema::connection('maestros')->getColumnListing($view);

    expect(end($columns))->toBe($column)
        ->and(array_slice($columns, -2, 1))->toBe(['sincronizado_en']);
})->with([
    'v_clientes' => ['v_clientes', 'contacto_principal'],
    'v_proveedores' => ['v_proveedores', 'contacto_principal'],
    'v_contactos' => ['v_contactos', 'telefono_2'],
]);

it('rolls contacto_principal and telefono_2 back, leaving the tables and views as they were', function () {
    $migration = require base_path('app/Modules/Sap/database/migrations/2026_11_02_000014_add_contacto_principal_and_telefono_2_to_maestros.php');
    $listing = fn (string $name): array => Schema::connection('maestros')->getColumnListing($name);
    $before = ['v_clientes' => $listing('v_clientes'), 'v_contactos' => $listing('v_contactos')];

    // The migrator runs a migration with its connection as the default one.
    DB::usingConnection('maestros', fn () => $migration->down());

    expect($listing('clientes'))->not->toContain('contacto_principal')
        ->and($listing('proveedores'))->not->toContain('contacto_principal')
        ->and($listing('contactos'))->not->toContain('telefono_2')
        ->and($listing('v_clientes'))->toBe(array_slice($before['v_clientes'], 0, -1))
        ->and($listing('v_contactos'))->toBe(array_slice($before['v_contactos'], 0, -1));

    DB::usingConnection('maestros', fn () => $migration->up());

    expect($listing('v_clientes'))->toBe($before['v_clientes'])
        ->and($listing('v_contactos'))->toBe($before['v_contactos']);
});

it('adds fecha_corte at the end of v_cartera, after every older column', function () {
    $columns = Schema::connection('cartera')->getColumnListing('v_cartera');

    expect(end($columns))->toBe('fecha_corte')
        ->and(array_slice($columns, -2, 1))->toBe(['sincronizado_en']);
});

it('rolls fecha_corte of v_cartera back, leaving the table and view as they were', function () {
    $migration = require base_path('app/Modules/Sap/database/migrations/2026_11_02_000015_add_fecha_corte_to_cartera.php');
    $listing = fn (string $name): array => Schema::connection('cartera')->getColumnListing($name);
    $before = $listing('v_cartera');

    DB::usingConnection('cartera', fn () => $migration->down());

    expect($listing('cartera'))->not->toContain('fecha_corte')
        ->and($listing('v_cartera'))->toBe(array_slice($before, 0, -1));

    DB::usingConnection('cartera', fn () => $migration->up());

    expect($listing('v_cartera'))->toBe($before);
});

it('adds kilos and then codigo_envio at the end of v_ventas, after every older column', function () {
    $columns = Schema::connection('ventas')->getColumnListing('v_ventas');

    expect(array_slice($columns, -3))->toBe(['sincronizado_en', 'kilos', 'codigo_envio']);
});

it('rolls codigo_envio back, leaving ventas and v_ventas as they were', function () {
    $migration = require base_path('app/Modules/Sap/database/migrations/2026_11_02_000018_add_codigo_envio_to_ventas.php');
    $listing = fn (string $name): array => Schema::connection('ventas')->getColumnListing($name);
    $before = $listing('v_ventas');

    DB::usingConnection('ventas', fn () => $migration->down());

    expect($listing('ventas'))->not->toContain('codigo_envio')
        ->and($listing('v_ventas'))->toBe(array_slice($before, 0, -1));

    DB::usingConnection('ventas', fn () => $migration->up());

    expect($listing('v_ventas'))->toBe($before);
});

it('rolls kilos back, leaving ventas and v_ventas as they were', function () {
    $later = require base_path('app/Modules/Sap/database/migrations/2026_11_02_000018_add_codigo_envio_to_ventas.php');
    $migration = require base_path('app/Modules/Sap/database/migrations/2026_11_02_000017_add_kilos_to_ventas.php');
    $listing = fn (string $name): array => Schema::connection('ventas')->getColumnListing($name);

    // Roll back in order: codigo_envio goes first, as migrate:rollback would.
    DB::usingConnection('ventas', fn () => $later->down());
    $before = $listing('v_ventas');

    DB::usingConnection('ventas', fn () => $migration->down());

    expect($listing('ventas'))->not->toContain('kilos')
        ->and($listing('v_ventas'))->toBe(array_slice($before, 0, -1));

    DB::usingConnection('ventas', fn () => $migration->up());

    expect($listing('v_ventas'))->toBe($before);
});
