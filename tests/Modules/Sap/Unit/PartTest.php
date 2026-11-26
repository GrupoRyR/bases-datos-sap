<?php

use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Domain\Columns\Column;
use App\Modules\Sap\Domain\Columns\ColumnType;

/*
| The parts and columns of docs/contrato-robot.md (sections 1, 5, 6, 10, 11 and 12).
| Any change here is a change of the contract: ask the user first.
*/

it('groups every part in exactly one dataset', function () {
    expect(Part::forDataset(Dataset::Maestros))->toBe([
        Part::Customers, Part::Suppliers, Part::Addresses, Part::Contacts, Part::Items,
        Part::ItemGroups, Part::Brands, Part::Prices, Part::SalesPeople,
        Part::CustomerGroups, Part::PaymentTerms, Part::Municipalities,
    ])->and(Part::forDataset(Dataset::Cartera))->toBe([Part::Receivables])
        ->and(Part::forDataset(Dataset::Ventas))->toBe([Part::Sales])
        ->and(Part::forDataset(Dataset::Pedidos))->toBe([Part::Orders])
        ->and(Part::forDataset(Dataset::Produccion))->toBe([
            Part::ProductionFinished, Part::PlantLoad, Part::ProductionCosts,
            Part::BillOfMaterials, Part::Routings, Part::StandardCosts,
        ]);
});

it('keeps each dataset on its connection, PEDIDOS and PRODUCCION next to VENTAS in ventas_sap', function () {
    expect(array_map(fn (Dataset $dataset): string => $dataset->connection(), Dataset::cases()))
        ->toBe(['maestros', 'cartera', 'ventas', 'ventas', 'ventas']);
});

it('keeps PRODUCCION for SGX only and every other dataset for both companies', function () {
    expect(Dataset::Produccion->companies())->toBe([Company::Sgx]);

    foreach ([Dataset::Maestros, Dataset::Cartera, Dataset::Ventas, Dataset::Pedidos] as $dataset) {
        expect($dataset->companies())->toBe([Company::Sgx, Company::Sdc]);
    }
});

it('replaces by date only the movement parts with a window', function () {
    $windowed = array_filter(Part::cases(), fn (Part $part): bool => $part->windowColumn() !== null);

    expect(array_map(fn (Part $part): string => "{$part->value}.{$part->windowColumn()}", array_values($windowed)))->toBe([
        'ventas.fecha_contabilizacion', 'produccion_terminado.fecha', 'produccion_carga_planta.fecha', 'produccion_costos.fecha',
    ]);

    foreach ($windowed as $part) {
        expect($part->columns()[$part->windowColumn()]->type)->toBe(ColumnType::Date)
            ->and($part->columns()[$part->windowColumn()]->required)->toBeTrue();
    }
});

it('uses the contract names for parts, tables and views', function () {
    expect(array_map(fn (Part $part): string => $part->value, Part::cases()))->toBe([
        'clientes', 'proveedores', 'direcciones', 'contactos', 'articulos', 'grupos_articulos',
        'marcas', 'precios', 'vendedores', 'grupos_clientes', 'condiciones_pago', 'municipios', 'cartera', 'ventas',
        'pedidos', 'produccion_terminado', 'produccion_carga_planta', 'produccion_costos', 'produccion_despiece',
        'produccion_rutas', 'produccion_costeo_teorico',
    ])->and(Part::Customers->table())->toBe('clientes')
        ->and(Part::Customers->view())->toBe('v_clientes')
        ->and(Part::Receivables->view())->toBe('v_cartera')
        ->and(Part::Sales->view())->toBe('v_ventas')
        ->and(Part::Orders->view())->toBe('v_pedidos')
        ->and(Part::ProductionCosts->view())->toBe('v_produccion_costos');
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
    [Part::Orders, ['doc_entry', 'linea']],
    [Part::ProductionFinished, ['doc_entry', 'linea']],
    // Two equal plant reports, or three cost facts per report, are legitimate.
    [Part::PlantLoad, []],
    [Part::ProductionCosts, []],
    // No key until SAP confirms father + child and item + operation never repeat.
    [Part::BillOfMaterials, []],
    [Part::Routings, []],
    [Part::StandardCosts, ['codigo_articulo']],
]);

it('lists exactly the columns of the contract', function (Part $part, array $columns) {
    expect(array_keys($part->columns()))->toBe($columns);
})->with([
    'socios' => [Part::Customers, [
        'codigo', 'nombre', 'nombre_extranjero', 'nit', 'grupo_codigo', 'vendedor_codigo',
        'condicion_pago_codigo', 'lista_precios_codigo', 'telefono', 'telefono_2', 'celular', 'correo',
        'ciudad', 'limite_credito', 'socio_vinculado', 'activo', 'actualizado_en_sap', 'creado_en_sap',
        'contacto_principal',
    ]],
    'direcciones' => [Part::Addresses, [
        'codigo_socio', 'tipo', 'nombre', 'calle', 'barrio', 'ciudad', 'municipio_codigo',
        'departamento', 'pais', 'codigo_postal',
    ]],
    'contactos' => [Part::Contacts, [
        'contacto_id', 'codigo_socio', 'nombre', 'nombres', 'apellidos', 'cargo', 'telefono',
        'celular', 'correo', 'activo', 'telefono_2',
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
        'precio_unitario', 'total', 'iva', 'ganancia_bruta', 'moneda', 'trm', 'comentarios', 'kilos', 'codigo_envio',
    ]],
    'pedidos' => [Part::Orders, [
        'doc_entry', 'numero_pedido', 'linea', 'fecha_pedido', 'fecha_compromiso', 'fecha_entrega_linea', 'dias',
        'rango', 'dias_atraso', 'slp_code', 'vendedor', 'canal', 'codigo_cliente', 'cliente', 'nit', 'ciudad',
        'id_pedido_app', 'oc_cliente', 'direccion_envio', 'comentarios', 'codigo_articulo', 'descripcion',
        'linea_articulo', 'familia', 'marca', 'bodega', 'unidad', 'cantidad_pedida', 'cantidad_pendiente',
        'precio_lista', 'precio_unitario', 'descuento_documento', 'total_pendiente', 'ganancia_bruta_pendiente',
        'moneda', 'trm',
    ]],
    'produccion_terminado' => [Part::ProductionFinished, [
        'doc_entry', 'numero_documento', 'linea', 'fecha', 'grupo', 'familia', 'codigo_articulo', 'articulo',
        'nro_ot', 'posicion', 'cantidad', 'valor',
    ]],
    'produccion_carga_planta' => [Part::PlantLoad, [
        'fecha', 'area', 'linea_producto', 'linea_negocio', 'etapa', 'puesto_trabajo', 'nro_ot', 'posicion',
        'operacion', 'codigo_articulo', 'nombre_articulo', 'unidad', 'unidades', 'unidades_no_conformes', 'horas',
        'almacen', 'estado_ot',
    ]],
    'produccion_costos' => [Part::ProductionCosts, [
        'fecha', 'concepto', 'area', 'linea_producto', 'linea_negocio', 'etapa', 'material_consumido',
        'grupo_material', 'codigo_material', 'nro_ot', 'posicion', 'codigo_articulo', 'nombre_articulo',
        'puesto_trabajo', 'costo',
    ]],
    'produccion_despiece' => [Part::BillOfMaterials, ['padre', 'hijo', 'cantidad', 'merma']],
    'produccion_rutas' => [Part::Routings, [
        'codigo_articulo', 'operacion', 'area', 'puesto', 'tiempo', 'cantidad_base', 'factor_merma',
    ]],
    'produccion_costeo_teorico' => [Part::StandardCosts, [
        'codigo_articulo', 'articulo', 'familia', 'posiciones', 'cantidad', 'material_soll', 'fabricacion_soll',
        'total_soll', 'total_ist',
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
        ])
        ->and($required(Part::Orders))->toBe([
            'doc_entry', 'numero_pedido', 'linea', 'fecha_pedido', 'fecha_compromiso', 'dias', 'rango', 'dias_atraso',
            'slp_code', 'codigo_cliente', 'codigo_articulo', 'cantidad_pedida', 'cantidad_pendiente', 'total_pendiente',
        ])
        ->and($required(Part::ProductionFinished))->toBe([
            'doc_entry', 'numero_documento', 'linea', 'fecha', 'grupo', 'familia', 'codigo_articulo', 'cantidad', 'valor',
        ])
        ->and($required(Part::PlantLoad))->toBe([
            'fecha', 'area', 'linea_producto', 'linea_negocio', 'etapa', 'nro_ot', 'posicion', 'operacion',
            'codigo_articulo', 'unidades',
        ])
        ->and($required(Part::ProductionCosts))->toBe([
            'fecha', 'concepto', 'area', 'linea_producto', 'linea_negocio', 'etapa', 'nro_ot', 'posicion',
            'codigo_articulo', 'costo',
        ])
        ->and($required(Part::BillOfMaterials))->toBe(['padre', 'hijo', 'cantidad'])
        ->and($required(Part::Routings))->toBe(['codigo_articulo', 'operacion'])
        ->and($required(Part::StandardCosts))->toBe(['codigo_articulo', 'familia', 'posiciones', 'cantidad']);

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
        ->and($of(ColumnType::Quantity))->toBe(['cantidad', 'trm', 'kilos'])
        ->and($of(ColumnType::Decimal))->toBe(['costo_unitario', 'costo_total', 'precio_lista', 'precio_unitario', 'total', 'iva', 'ganancia_bruta'])
        ->and($of(ColumnType::Text))->toHaveCount(20)
        ->and(Part::Sales->columns()['codigo_envio']->length)->toBe(50);
});

it('types the PEDIDOS columns as contract section 11 says', function () {
    $types = array_map(fn (Column $column): ColumnType => $column->type, Part::Orders->columns());
    $of = fn (ColumnType $type): array => array_keys(array_filter($types, fn (ColumnType $found): bool => $found === $type));

    expect($of(ColumnType::Integer))->toBe(['doc_entry', 'numero_pedido', 'linea', 'dias', 'dias_atraso', 'slp_code'])
        ->and($of(ColumnType::Date))->toBe(['fecha_pedido', 'fecha_compromiso', 'fecha_entrega_linea'])
        ->and($of(ColumnType::Quantity))->toBe(['cantidad_pedida', 'cantidad_pendiente', 'descuento_documento', 'trm'])
        ->and($of(ColumnType::Decimal))->toBe(['precio_lista', 'precio_unitario', 'total_pendiente', 'ganancia_bruta_pendiente'])
        ->and($of(ColumnType::Text))->toHaveCount(19)
        // Days late are negative while the order is not due; no column has a minimum.
        ->and(array_filter(Part::Orders->columns(), fn (Column $column): bool => $column->min !== null || $column->omittable))->toBe([]);
});

it('types the PRODUCCION columns as contract section 12 says', function (Part $part, array $integers, array $quantities, array $amounts) {
    $types = array_map(fn (Column $column): ColumnType => $column->type, $part->columns());
    $of = fn (ColumnType $type): array => array_keys(array_filter($types, fn (ColumnType $found): bool => $found === $type));

    expect($of(ColumnType::Integer))->toBe($integers)
        ->and($of(ColumnType::Quantity))->toBe($quantities)
        ->and($of(ColumnType::Decimal))->toBe($amounts)
        ->and($of(ColumnType::Date))->toBe(isset($types['fecha']) ? ['fecha'] : [])
        ->and(array_filter($part->columns(), fn (Column $column): bool => $column->min !== null || $column->omittable))->toBe([]);
})->with([
    'produccion_terminado' => [Part::ProductionFinished, ['doc_entry', 'numero_documento', 'linea', 'nro_ot', 'posicion'], ['cantidad'], ['valor']],
    'produccion_carga_planta' => [Part::PlantLoad, ['nro_ot', 'posicion', 'operacion'], ['unidades', 'unidades_no_conformes', 'horas'], []],
    'produccion_costos' => [Part::ProductionCosts, ['nro_ot', 'posicion'], [], ['costo']],
    'produccion_despiece' => [Part::BillOfMaterials, [], ['cantidad', 'merma'], []],
    'produccion_rutas' => [Part::Routings, ['operacion'], ['tiempo', 'cantidad_base', 'factor_merma'], []],
    'produccion_costeo_teorico' => [Part::StandardCosts, ['posiciones'], ['cantidad'], ['material_soll', 'fabricacion_soll', 'total_soll', 'total_ist']],
]);

it('accepts only the five cost concepts of the contract, written exactly', function () {
    expect(Part::ProductionCosts->columns()['concepto']->values)->toBe([
        'Mano de obra directa', 'Costo variable', 'Costo fijo', 'Material comprado', 'Material intermedio',
    ]);
});

it('knows which parts carry the SAP update time used for changes', function () {
    $tracked = array_values(array_filter(Part::cases(), fn (Part $part): bool => $part->tracksSapUpdates()));

    expect($tracked)->toBe([Part::Customers, Part::Suppliers, Part::Items]);
});
