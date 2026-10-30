<?php

use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Domain\Columns\Column;
use App\Modules\Sap\Domain\Columns\ColumnType;

/*
| The parts and columns of docs/contrato-robot.md (sections 1, 5, 6 and 10).
| Any change here is a change of the contract: ask the user first.
*/

it('groups every part in exactly one dataset', function () {
    expect(Part::forDataset(Dataset::Maestros))->toBe([
        Part::Customers, Part::Suppliers, Part::Addresses, Part::Contacts, Part::Items,
        Part::ItemGroups, Part::Brands, Part::Prices, Part::SalesPeople,
        Part::CustomerGroups, Part::PaymentTerms, Part::Municipalities,
    ])->and(Part::forDataset(Dataset::Cartera))->toBe([Part::Receivables])
        ->and(Part::forDataset(Dataset::Ventas))->toBe([Part::Sales]);
});

it('keeps each dataset on its own connection', function () {
    expect(array_map(fn (Dataset $dataset): string => $dataset->connection(), Dataset::cases()))
        ->toBe(['maestros', 'cartera', 'ventas']);
});

it('uses the contract names for parts, tables and views', function () {
    expect(array_map(fn (Part $part): string => $part->value, Part::cases()))->toBe([
        'clientes', 'proveedores', 'direcciones', 'contactos', 'articulos', 'grupos_articulos',
        'marcas', 'precios', 'vendedores', 'grupos_clientes', 'condiciones_pago', 'municipios', 'cartera', 'ventas',
    ])->and(Part::Customers->table())->toBe('clientes')
        ->and(Part::Customers->view())->toBe('v_clientes')
        ->and(Part::Receivables->view())->toBe('v_cartera')
        ->and(Part::Sales->view())->toBe('v_ventas');
});

it('keys each part as the contract says', function (Part $part, array $key) {
    expect($part->key())->toBe($key);
})->with([
    [Part::Customers, ['codigo']],
    [Part::Suppliers, ['codigo']],
    [Part::Addresses, ['codigo_socio', 'tipo', 'nombre']],
    [Part::Contacts, ['contacto_id']],
    [Part::Items, ['codigo']],
    [Part::ItemGroups, ['codigo']],
    [Part::Brands, ['codigo']],
    [Part::Prices, ['articulo_codigo']],
    [Part::SalesPeople, ['codigo']],
    [Part::CustomerGroups, ['codigo']],
    [Part::PaymentTerms, ['codigo']],
    [Part::Municipalities, ['codigo']],
    // CARTERA has no natural key: every close replaces the whole company.
    [Part::Receivables, []],
    [Part::Sales, ['tipo_objeto', 'doc_entry', 'linea']],
]);

it('lists exactly the columns of the contract', function (Part $part, array $columns) {
    expect(array_keys($part->columns()))->toBe($columns);
})->with([
    'socios' => [Part::Customers, [
        'codigo', 'nombre', 'nombre_extranjero', 'nit', 'grupo_codigo', 'vendedor_codigo',
        'condicion_pago_codigo', 'lista_precios_codigo', 'telefono', 'telefono_2', 'celular', 'correo',
        'ciudad', 'limite_credito', 'socio_vinculado', 'activo', 'actualizado_en_sap', 'creado_en_sap',
    ]],
    'direcciones' => [Part::Addresses, [
        'codigo_socio', 'tipo', 'nombre', 'calle', 'barrio', 'ciudad', 'municipio_codigo',
        'departamento', 'pais', 'codigo_postal',
    ]],
    'contactos' => [Part::Contacts, [
        'contacto_id', 'codigo_socio', 'nombre', 'nombres', 'apellidos', 'cargo', 'telefono',
        'celular', 'correo', 'activo',
    ]],
    'articulos' => [Part::Items, [
        'codigo', 'nombre', 'nombre_extranjero', 'grupo_codigo', 'marca_codigo', 'unidad_venta',
        'codigo_barras', 'inventariable', 'de_venta', 'de_compra', 'activo', 'actualizado_en_sap', 'creado_en_sap',
    ]],
    'grupos_articulos' => [Part::ItemGroups, ['codigo', 'nombre', 'activo']],
    'marcas' => [Part::Brands, ['codigo', 'nombre', 'activo']],
    'grupos_clientes' => [Part::CustomerGroups, ['codigo', 'nombre', 'activo']],
    'municipios' => [Part::Municipalities, ['codigo', 'nombre', 'activo']],
    'precios' => [Part::Prices, ['articulo_codigo', 'lista_codigo', 'lista_nombre', 'precio', 'moneda', 'activo']],
    'vendedores' => [Part::SalesPeople, ['codigo', 'nombre', 'correo', 'celular', 'activo']],
    'condiciones_pago' => [Part::PaymentTerms, ['codigo', 'nombre', 'dias_extra', 'meses_extra', 'activo']],
    'cartera' => [Part::Receivables, [
        'codigo_sn', 'slp_code', 'email_asesor', 'nombre_sn', 'nit', 'grupo', 'municipio', 'cuenta_visible',
        'tipo_doc', 'documento', 'documento_base', 'referencia_1', 'no_referencia', 'asesor', 'total_plazos',
        'no_plazo', 'condicion_pago', 'fecha_contabilizacion', 'fecha_vencimiento', 'fecha_documento', 'dias',
        'limite_credito', 'importe_original', 'base_gravable', 'saldo_base', 'saldo_vencido', 'valor_abonado',
        'sin_vencer', 'valor_cheques', 'd_0_30', 'd_31_60', 'd_61_90', 'd_91_120', 'd_121_150', 'd_151_180',
        'd_mas_180', 'saldo', 'rango',
    ]],
    'ventas' => [Part::Sales, [
        'tipo_objeto', 'doc_entry', 'numero_documento', 'linea', 'clase_documento', 'estado_documento',
        'fecha_documento', 'fecha_contabilizacion', 'slp_code', 'vendedor', 'canal', 'codigo_cliente', 'cliente',
        'nit', 'ciudad', 'pedido', 'id_pedido_app', 'oc_cliente', 'ciudad_envio', 'direccion_envio', 'marca',
        'familia', 'codigo_articulo', 'descripcion', 'cantidad', 'costo_unitario', 'costo_total', 'precio_lista',
        'precio_unitario', 'total', 'iva', 'moneda', 'trm', 'comentarios',
    ]],
]);

it('gives the suppliers the same columns as the customers', function () {
    expect(Part::Suppliers->columns())->toEqual(Part::Customers->columns());
});

it('marks the key columns and the bold columns of the contract as required', function () {
    $required = fn (Part $part): array => array_keys(array_filter($part->columns(), fn (Column $column): bool => $column->required));

    expect($required(Part::Customers))->toBe(['codigo', 'nombre', 'activo', 'actualizado_en_sap'])
        ->and($required(Part::Addresses))->toBe(['codigo_socio', 'tipo', 'nombre'])
        ->and($required(Part::Contacts))->toBe(['contacto_id', 'codigo_socio', 'nombre', 'activo'])
        ->and($required(Part::Prices))->toBe(['articulo_codigo', 'lista_codigo', 'lista_nombre', 'activo'])
        ->and($required(Part::Receivables))->toBe(['codigo_sn', 'documento', 'fecha_vencimiento', 'dias', 'saldo'])
        ->and($required(Part::Sales))->toBe([
            'tipo_objeto', 'doc_entry', 'numero_documento', 'linea', 'clase_documento', 'estado_documento',
            'fecha_documento', 'fecha_contabilizacion', 'slp_code', 'codigo_cliente', 'cantidad', 'total',
        ]);

    foreach (Part::cases() as $part) {
        foreach ($part->key() as $key) {
            expect($part->columns()[$key]->required)->toBeTrue();
        }
    }
});

it('types the columns as the contract says', function () {
    $receivables = Part::Receivables->columns();

    expect($receivables['slp_code']->type)->toBe(ColumnType::Integer)
        ->and($receivables['dias']->type)->toBe(ColumnType::Integer)
        ->and($receivables['fecha_vencimiento']->type)->toBe(ColumnType::Date)
        ->and($receivables['d_mas_180']->type)->toBe(ColumnType::Decimal)
        ->and($receivables['rango']->type)->toBe(ColumnType::Text)
        ->and(Part::Customers->columns()['actualizado_en_sap']->type)->toBe(ColumnType::DateTime)
        ->and(Part::Customers->columns()['limite_credito']->type)->toBe(ColumnType::Decimal)
        ->and(Part::Items->columns()['inventariable']->type)->toBe(ColumnType::Boolean)
        ->and(Part::Contacts->columns()['contacto_id']->type)->toBe(ColumnType::Integer)
        ->and(Part::SalesPeople->columns()['codigo']->min)->toBe(0);
});

it('types the VENTAS columns as contract section 10 says', function () {
    $types = array_map(fn (Column $column): ColumnType => $column->type, Part::Sales->columns());
    $of = fn (ColumnType $type): array => array_keys(array_filter($types, fn (ColumnType $found): bool => $found === $type));

    expect($of(ColumnType::Integer))->toBe(['tipo_objeto', 'doc_entry', 'numero_documento', 'linea', 'slp_code'])
        ->and($of(ColumnType::Date))->toBe(['fecha_documento', 'fecha_contabilizacion'])
        ->and($of(ColumnType::Quantity))->toBe(['cantidad', 'trm'])
        ->and($of(ColumnType::Decimal))->toBe(['costo_unitario', 'costo_total', 'precio_lista', 'precio_unitario', 'total', 'iva'])
        ->and($of(ColumnType::Text))->toHaveCount(19);
});

it('knows which parts carry the SAP update time used for changes', function () {
    $tracked = array_values(array_filter(Part::cases(), fn (Part $part): bool => $part->tracksSapUpdates()));

    expect($tracked)->toBe([Part::Customers, Part::Suppliers, Part::Items]);
});
