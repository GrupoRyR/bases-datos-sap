<?php

namespace App\Modules\Sap\Domain\Columns;

use App\Modules\Sap\Contracts\Enums\Part;

/**
 * The columns of each part, exactly as docs/contrato-robot.md lists them
 * (sections 5.2, 6 and 10), with the SAP source in the comments. Changing this
 * list changes the contract: the user approves it first.
 */
final class PartColumns
{
    /**
     * Built once per part: batch validation asks for them on every row.
     *
     * @var array<string, array<string, Column>>
     */
    private static array $cache = [];

    /**
     * @return array<string, Column>
     */
    public static function for(Part $part): array
    {
        return self::$cache[$part->value] ??= self::build($part);
    }

    /**
     * @return array<string, Column>
     */
    private static function build(Part $part): array
    {
        $columns = match ($part) {
            Part::Customers, Part::Suppliers => self::businessPartners(),
            Part::Addresses => [
                Column::text('codigo_socio', 50, required: true),   // CRD1.CardCode
                Column::text('tipo', 1, required: true),            // AdresType: B billing, S shipping
                Column::text('nombre', 50, required: true),         // Address
                Column::text('calle'),                              // Street
                Column::text('barrio'),                             // Block
                Column::text('ciudad'),                             // City
                Column::text('municipio_codigo', 50),               // County
                Column::text('departamento'),                       // State
                Column::text('pais', 50),                           // Country
                Column::text('codigo_postal', 50),                  // ZipCode
            ],
            Part::Contacts => [
                Column::integer('contacto_id', required: true),     // OCPR.CntctCode
                Column::text('codigo_socio', 50, required: true),   // CardCode
                Column::text('nombre', required: true),             // Name
                Column::text('nombres'),                            // FirstName
                Column::text('apellidos'),                          // LastName
                Column::text('cargo'),                              // Position
                Column::text('telefono', 50),                       // Tel1
                Column::text('celular', 50),                        // Cellolar
                Column::text('correo'),                             // E_MailL
                Column::boolean('activo', required: true),          // Active = Y
            ],
            Part::Items => [
                Column::text('codigo', 50, required: true),         // OITM.ItemCode
                Column::text('nombre', required: true),             // ItemName
                Column::text('nombre_extranjero'),                  // FrgnName
                Column::integer('grupo_codigo'),                    // ItmsGrpCod
                Column::integer('marca_codigo'),                    // FirmCode
                Column::text('unidad_venta', 50),                   // SalUnitMsr
                Column::text('codigo_barras'),                      // CodeBars
                Column::boolean('inventariable'),                   // InvntItem
                Column::boolean('de_venta'),                        // SellItem
                Column::boolean('de_compra'),                       // PrchseItem
                Column::boolean('activo', required: true),          // not validFor = N nor frozenFor = Y
                Column::dateTime('actualizado_en_sap', required: true),
                Column::date('creado_en_sap'),                      // CreateDate
            ],
            Part::ItemGroups => self::catalog(),                    // OITB: ItmsGrpCod, ItmsGrpNam
            Part::Brands => self::catalog(),                        // OMRC: FirmCode, FirmName
            Part::Prices => [
                Column::text('articulo_codigo', 50, required: true), // ITM1.ItemCode
                Column::integer('lista_codigo', required: true),     // PriceList
                Column::text('lista_nombre', required: true),        // OPLN.ListName
                Column::decimal('precio'),                           // Price
                Column::text('moneda', 10),                          // Currency
                Column::boolean('activo', required: true),
            ],
            Part::SalesPeople => [
                Column::integer('codigo', required: true, min: 0),  // OSLP.SlpCode
                Column::text('nombre', required: true),             // SlpName
                Column::text('correo'),                             // Email
                Column::text('celular', 50),                        // Mobil
                Column::boolean('activo', required: true),          // Active = Y
            ],
            Part::CustomerGroups => self::catalog(),                // OCRG (GroupType C): GroupCode, GroupName
            Part::PaymentTerms => [
                Column::integer('codigo', required: true),          // OCTG.GroupNum
                Column::text('nombre', required: true),             // PymntGroup
                Column::integer('dias_extra'),                      // ExtraDays
                Column::integer('meses_extra'),                     // ExtraMonth
                Column::boolean('activo', required: true),
            ],
            Part::Municipalities => [
                Column::text('codigo', 50, required: true),         // @HBT_MUNICIPIO.Code
                Column::text('nombre', required: true),             // Name
                Column::boolean('activo', required: true),
            ],
            Part::Receivables => self::receivables(),
            Part::Sales => self::sales(),
        };

        $byName = [];

        foreach ($columns as $column) {
            $byName[$column->name] = $column;
        }

        return $byName;
    }

    /**
     * OCRD, for customers (CardType C) and suppliers (CardType S).
     *
     * @return list<Column>
     */
    private static function businessPartners(): array
    {
        return [
            Column::text('codigo', 50, required: true),             // CardCode
            Column::text('nombre', required: true),                 // CardName
            Column::text('nombre_extranjero'),                      // CardFName
            Column::text('nit', 50),                                // LicTradNum
            Column::integer('grupo_codigo'),                        // GroupCode
            Column::integer('vendedor_codigo'),                     // SlpCode, -1 without one
            Column::integer('condicion_pago_codigo'),               // GroupNum
            Column::integer('lista_precios_codigo'),                // ListNum
            Column::text('telefono', 50),                           // Phone1
            Column::text('telefono_2', 50),                         // Phone2
            Column::text('celular', 50),                            // Cellular
            Column::text('correo'),                                 // E_Mail
            Column::text('ciudad'),                                 // City
            Column::decimal('limite_credito'),                      // CreditLine
            Column::text('socio_vinculado', 50),                    // ConnBP
            Column::boolean('activo', required: true),              // not validFor = N nor frozenFor = Y
            Column::dateTime('actualizado_en_sap', required: true), // UpdateDate + UpdateTS
            Column::date('creado_en_sap'),                          // CreateDate
        ];
    }

    /**
     * A catalog with an integer code, a name and no flag of its own.
     *
     * @return list<Column>
     */
    private static function catalog(): array
    {
        return [
            Column::integer('codigo', required: true),
            Column::text('nombre', required: true),
            Column::boolean('activo', required: true),
        ];
    }

    /**
     * The columns of etl/esquema.py of the gestor de cartera (batch
     * "cartera"), with the same names, so it can read from here unchanged.
     *
     * @return list<Column>
     */
    private static function receivables(): array
    {
        $amounts = [
            'limite_credito', 'importe_original', 'base_gravable', 'saldo_base', 'saldo_vencido',
            'valor_abonado', 'sin_vencer', 'valor_cheques', 'd_0_30', 'd_31_60', 'd_61_90',
            'd_91_120', 'd_121_150', 'd_151_180', 'd_mas_180',
        ];

        return [
            Column::text('codigo_sn', 50, required: true),
            Column::integer('slp_code'),
            Column::text('email_asesor'),
            Column::text('nombre_sn'),
            Column::text('nit', 50),
            Column::text('grupo'),
            Column::text('municipio'),
            Column::text('cuenta_visible'),
            Column::text('tipo_doc', 50),
            Column::text('documento', 50, required: true),
            Column::text('documento_base', 50),
            Column::text('referencia_1'),
            Column::text('no_referencia'),
            Column::text('asesor'),
            Column::integer('total_plazos'),
            Column::integer('no_plazo'),
            Column::text('condicion_pago'),
            Column::date('fecha_contabilizacion'),
            Column::date('fecha_vencimiento', required: true),
            Column::date('fecha_documento'),
            Column::integer('dias', required: true),
            ...array_map(fn (string $name): Column => Column::decimal($name), $amounts),
            Column::decimal('saldo', required: true),
            Column::text('rango', 50),
        ];
    }

    /**
     * The columns of etl/esquema.py of the gestor de cartera (batch
     * "ventas"), with the same names and order: one row per invoice or
     * credit note line (contract section 10). Credit notes bring negative
     * quantity, cost, total and VAT; unit prices and costs come unsigned.
     *
     * @return list<Column>
     */
    private static function sales(): array
    {
        return [
            Column::integer('tipo_objeto', required: true),         // ObjType: 13 invoice, 14 credit note
            Column::integer('doc_entry', required: true),           // DocEntry
            Column::integer('numero_documento', required: true),    // DocNum
            Column::integer('linea', required: true),               // LineNum
            Column::text('clase_documento', 20, required: true),    // factura, nota_debito or nota_credito
            Column::text('estado_documento', 20, required: true),   // anulado, anulacion, cerrado or abierto
            Column::date('fecha_documento', required: true),        // TaxDate, reference only
            Column::date('fecha_contabilizacion', required: true),  // DocDate: the month of the sale and the window
            Column::integer('slp_code', required: true),            // SlpCode, -1 without one
            Column::text('vendedor'),
            Column::text('canal'),
            Column::text('codigo_cliente', 50, required: true),     // CardCode
            Column::text('cliente'),
            Column::text('nit', 50),
            Column::text('ciudad'),
            Column::text('pedido'),
            Column::text('id_pedido_app'),                          // OINV.U_SGX_IdPedidoApp, only SGX
            Column::text('oc_cliente'),
            Column::text('ciudad_envio'),
            Column::text('direccion_envio'),
            Column::text('marca'),
            Column::text('familia'),
            Column::text('codigo_articulo', 50),                    // ItemCode
            Column::text('descripcion'),
            Column::quantity('cantidad', required: true),
            Column::decimal('costo_unitario'),
            Column::decimal('costo_total'),
            Column::decimal('precio_lista'),
            Column::decimal('precio_unitario'),
            Column::decimal('total', required: true),
            Column::decimal('iva'),
            Column::text('moneda', 10),
            Column::quantity('trm'),
            Column::text('comentarios'),
        ];
    }
}
