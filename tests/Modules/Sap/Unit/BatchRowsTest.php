<?php

use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Domain\Batches\BatchRows;
use Tests\Modules\Sap\Support\RobotClient;

/*
| How a batch's rows are checked and normalized (docs/contrato-robot.md,
| section 4.2): exact columns in any order, one value per column, typed
| values, required columns never null or empty.
*/

/**
 * @param  array<string, mixed>  $overrides
 * @return array{rows: list<list<mixed>>, errors: array<string, string>}
 */
function checkOneCustomer(array $overrides): array
{
    $body = RobotClient::batch(1, Part::Customers, [RobotClient::row(Part::Customers, $overrides)]);

    return BatchRows::check(Part::Customers, $body['columns'], $body['rows']);
}

it('normalizes a valid row into the column order of the part', function () {
    $columns = ['activo', 'codigo', 'nombre', 'actualizado_en_sap', ...array_diff(array_keys(Part::Customers->columns()), ['activo', 'codigo', 'nombre', 'actualizado_en_sap'])];
    $values = array_fill(0, count($columns), null);
    [$values[0], $values[1], $values[2], $values[3]] = [false, '  C800123456 ', 'Ferretería La Llave SAS', '2026-10-23T14:15:02Z'];

    $result = BatchRows::check(Part::Customers, $columns, [$values]);
    $row = array_combine(array_keys(Part::Customers->columns()), $result['rows'][0]);

    expect($result['errors'])->toBe([])
        ->and($row['codigo'])->toBe('C800123456')
        ->and($row['activo'])->toBeFalse()
        // Stored in the app timezone, America/Bogota.
        ->and($row['actualizado_en_sap'])->toBe('2026-10-23 09:15:02');
});

it('requires exactly the columns of the part, without repeats', function (array $columns, string $message) {
    $result = BatchRows::check(Part::Brands, $columns, [[1, 'Acme', true]]);

    expect($result['errors'])->toHaveKey('columns')
        ->and($result['errors']['columns'])->toContain($message);
})->with([
    'missing' => [['codigo', 'nombre'], 'Faltan columnas: activo'],
    'unknown' => [['codigo', 'nombre', 'activo', 'color'], 'Columnas desconocidas: color'],
    'repeated' => [['codigo', 'nombre', 'nombre'], 'Columnas repetidas: nombre'],
]);

it('refuses a row without one value per column', function () {
    $result = BatchRows::check(Part::Brands, ['codigo', 'nombre', 'activo'], [[1, 'Acme']]);

    expect($result['errors'])->toBe(['rows.0' => 'La fila debe traer un valor por columna.']);
});

it('checks every type as the contract says', function (array $overrides, string $column, string $message) {
    expect(checkOneCustomer($overrides)['errors'])->toBe(["rows.0.{$column}" => $message]);
})->with([
    'required null' => [['nombre' => null], 'nombre', 'Es obligatoria.'],
    'required blank' => [['nombre' => '   '], 'nombre', 'Es obligatoria.'],
    'text as number' => [['nit' => 800123456], 'nit', 'Debe ser texto.'],
    'text over 4,000' => [['ciudad' => str_repeat('a', 4001)], 'ciudad', 'Pasa de 4.000 caracteres.'],
    'key over its length' => [['codigo' => str_repeat('C', 51)], 'codigo', 'Pasa de 50 caracteres.'],
    'integer as text' => [['grupo_codigo' => '100'], 'grupo_codigo', 'Debe ser un entero.'],
    'integer out of range' => [['grupo_codigo' => 3000000000], 'grupo_codigo', 'Debe ser un entero.'],
    'amount as number' => [['limite_credito' => 1000.5], 'limite_credito', 'Debe ser un monto como texto, con punto y hasta 2 decimales.'],
    'amount with comma' => [['limite_credito' => '1.000,50'], 'limite_credito', 'Debe ser un monto como texto, con punto y hasta 2 decimales.'],
    'amount with 3 decimals' => [['limite_credito' => '10.505'], 'limite_credito', 'Debe ser un monto como texto, con punto y hasta 2 decimales.'],
    'boolean as text' => [['activo' => 'Y'], 'activo', 'Debe ser true o false.'],
    'impossible date' => [['creado_en_sap' => '2026-02-30'], 'creado_en_sap', 'Debe ser una fecha AAAA-MM-DD.'],
    'time without offset' => [['actualizado_en_sap' => '2026-10-23T09:15:02'], 'actualizado_en_sap', 'Debe ser una hora ISO 8601 con zona.'],
]);

it('enforces the minimum of an integer column', function () {
    $result = BatchRows::check(Part::SalesPeople, ['codigo', 'nombre', 'correo', 'celular', 'activo'], [[-1, 'Sin vendedor', null, null, true]]);

    expect($result['errors'])->toBe(['rows.0.codigo' => 'Debe ser mayor o igual a 0.']);
});

it('cuts optional text to its column and keeps negative amounts', function () {
    $result = checkOneCustomer(['nombre_extranjero' => str_repeat('n', 300), 'limite_credito' => '-1234567.8']);
    $row = array_combine(array_keys(Part::Customers->columns()), $result['rows'][0]);

    expect($result['errors'])->toBe([])
        ->and(mb_strlen($row['nombre_extranjero']))->toBe(255)
        ->and($row['limite_credito'])->toBe('-1234567.8');
});

it('reports at most 50 errors', function () {
    $rows = array_fill(0, 60, RobotClient::row(Part::Customers, ['nombre' => null]));
    $body = RobotClient::batch(1, Part::Customers, $rows);

    expect(BatchRows::check(Part::Customers, $body['columns'], $body['rows'])['errors'])->toHaveCount(50);
});

it('hashes the key of a row so equal keys match exactly', function () {
    $key = fn (array $overrides): string => BatchRows::keyHash(Part::Addresses, BatchRows::check(
        Part::Addresses,
        array_keys(Part::Addresses->columns()),
        [array_values(RobotClient::row(Part::Addresses, $overrides))],
    )['rows'][0]);

    expect($key(['nombre' => 'Bodega']))->toBe($key(['nombre' => 'Bodega', 'calle' => 'Cra 7']))
        ->and($key(['nombre' => 'Bodega']))->not->toBe($key(['nombre' => 'BODEGA']));
});

/**
 * @param  array<string, mixed>  $overrides
 * @return array{rows: list<list<mixed>>, errors: array<string, string>}
 */
function checkOneSale(array $overrides): array
{
    $body = RobotClient::batch(1, Part::Sales, [RobotClient::row(Part::Sales, $overrides)]);

    return BatchRows::check(Part::Sales, $body['columns'], $body['rows']);
}

it('keeps quantities and rates with up to 6 decimals and negative credit note amounts', function () {
    $result = checkOneSale([
        'tipo_objeto' => 14, 'cantidad' => '-2.500000', 'trm' => '4123.456789',
        'costo_total' => '-1500.25', 'total' => '-2380.00', 'iva' => '-380', 'precio_unitario' => '952.38',
    ]);
    $row = array_combine(array_keys(Part::Sales->columns()), $result['rows'][0]);

    expect($result['errors'])->toBe([])
        ->and($row['cantidad'])->toBe('-2.500000')
        ->and($row['trm'])->toBe('4123.456789')
        ->and($row['total'])->toBe('-2380.00')
        ->and($row['iva'])->toBe('-380');
});

it('checks quantities and rates as decimal text with up to 6 decimals', function (mixed $value) {
    expect(checkOneSale(['cantidad' => $value])['errors'])
        ->toBe(['rows.0.cantidad' => 'Debe ser una cantidad como texto, con punto y hasta 6 decimales.']);
})->with([
    'as number' => [2.5],
    'with 7 decimals' => ['2.5000001'],
    'with comma' => ['2,5'],
    'over 13 digits' => ['12345678901234'],
]);

it('keeps amounts of VENTAS to 2 decimals', function () {
    expect(checkOneSale(['total' => '10.505'])['errors'])
        ->toBe(['rows.0.total' => 'Debe ser un monto como texto, con punto y hasta 2 decimales.']);
});
