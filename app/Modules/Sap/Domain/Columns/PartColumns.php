<?php

namespace App\Modules\Sap\Domain\Columns;

use App\Modules\Sap\Contracts\Enums\Part;

/**
 * The columns of each part, exactly as docs/contrato-robot.md lists them
 * (sections 5.2, 6, 10 and 11.2), with the SAP source in the comments. Changing this
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

    /** The ranges of an open order line by its days, exact ASCII texts (contract section 11.2). */
    private const ORDER_RANGES = ['Hasta 30 dias', 'De 31 a 60 dias', 'De 61 a 90 dias', 'Mas de 90 dias'];

    /** The cost concepts of produccion_costos (contract section 12.2), exact ASCII texts. */
    private const COST_CONCEPTS = ['Mano de obra directa', 'Costo variable', 'Costo fijo', 'Material comprado', 'Material intermedio'];

    /** The columns a complemento run brings of each sales line (contract section 10.5), in contract order. */
    private const SALES_COMPLEMENT = ['tipo_objeto', 'doc_entry', 'linea', 'fecha_contabilizacion', 'kilos', 'codigo_envio'];

    /** @var array<string, Column>|null */
    private static ?array $salesComplement = null;

    /**
     * @return array<string, Column>
     */
    public static function for(Part $part): array
    {
        return self::$cache[$part->value] ??= self::build($part);
    }

    /**
     * The reduced header of a complemento run (contract section 10.5): the
     * key of the sales line, its posting date for the range, its weight and
     * its shipping code, which here are not omittable, since filling them is
     * the whole run. Their values may still be null, as in a full run, when
     * SAP has no weight or shipping code for the line.
     *
     * @return array<string, Column>
     */
    public static function salesComplement(): array
    {
        return self::$salesComplement ??= [
            ...array_intersect_key(self::for(Part::Sales), array_flip(self::SALES_COMPLEMENT)),
            'kilos' => Column::quantity('kilos'),
            'codigo_envio' => Column::text('codigo_envio', 50),
        ];
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
                // Tel2. Omittable until the robot sends it (contract section 4.2).
                Column::text('telefono_2', 50, omittable: true),
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
            Part::Orders => self::orders(),
            Part::ProductionFinished => [
                Column::integer('doc_entry', required: true),          // OIGN.DocEntry
                Column::integer('numero_documento', required: true),   // OIGN.DocNum
                Column::integer('linea', required: true),              // IGN1.LineNum
                Column::date('fecha', required: true),                 // OIGN.DocDate: the window
                Column::text('grupo', required: true),                 // OITB.ItmsGrpNam
                Column::text('familia', required: true),               // OITM.U_GSP_FAMILIA
                Column::text('codigo_articulo', 50, required: true),   // IGN1.ItemCode
                Column::text('articulo'),                              // IGN1.Dscription
                Column::integer('nro_ot'),                             // IGN1.U_beas_belnrid
                Column::integer('posicion'),                           // IGN1.U_beas_belposid
                Column::quantity('cantidad', required: true),          // IGN1.Quantity
                Column::decimal('valor', required: true),              // IGN1.LineTotal
            ],
            Part::PlantLoad => [
                Column::date('fecha', required: true),                 // BEAS_ARBZEIT.DocDate: the window
                ...self::productionArea(),
                Column::text('puesto_trabajo'),                        // BEAS_APLATZ.BEZ
                Column::integer('nro_ot', required: true),             // BEAS_ARBZEIT.BELNR_ID
                Column::integer('posicion', required: true),           // BEAS_ARBZEIT.BELPOS_ID
                Column::integer('operacion', required: true),          // BEAS_ARBZEIT.POS_ID
                Column::text('codigo_articulo', 50, required: true),   // BEAS_FTPOS.ItemCode
                Column::text('nombre_articulo'),                       // BEAS_FTPOS.ItemName
                Column::text('unidad', 100),                           // BEAS_FTPOS.ME_VERBRAUCH
                Column::quantity('unidades', required: true),          // BEAS_ARBZEIT.MENGE_GUT
                Column::quantity('unidades_no_conformes'),             // BEAS_ARBZEIT.MENGE_SCHLECHT
                Column::quantity('horas'),                             // BEAS_ARBZEIT.ZEIT / 60
                Column::text('almacen', 50),                           // BEAS_FTPOS.WhsCode
                Column::text('estado_ot', 10),                         // BEAS_FTPOS.ABGKZ, J or N
            ],
            Part::ProductionCosts => [
                Column::date('fecha', required: true),                 // BEAS_ARBZEIT or OIGE DocDate: the window
                Column::text('concepto', 30, required: true, values: self::COST_CONCEPTS),
                ...self::productionArea(),
                Column::text('material_consumido'),                    // IGE1.Dscription
                Column::text('grupo_material'),                        // OITB.ItmsGrpNam of the material
                Column::text('codigo_material', 50),                   // IGE1.ItemCode
                Column::integer('nro_ot', required: true),             // BELNR_ID or IGE1.U_beas_belnrid
                Column::integer('posicion', required: true),           // BELPOS_ID or IGE1.U_beas_belposid
                Column::text('codigo_articulo', 50, required: true),   // BEAS_FTPOS.ItemCode, the item made
                Column::text('nombre_articulo'),                       // BEAS_FTPOS.ItemName
                Column::text('puesto_trabajo'),                        // BEAS_APLATZ.BEZ
                Column::decimal('costo', required: true),
            ],
            Part::BillOfMaterials => [
                Column::text('padre', 50, required: true),             // BEAS_STL.ItemCode
                Column::text('hijo', 50, required: true),              // BEAS_STL.ART1_ID
                Column::quantity('cantidad', required: true),          // BEAS_STL.MENGE_VERBRAUCH
                Column::quantity('merma'),                             // BEAS_STL.AUSSCHUSS
            ],
            Part::Routings => [
                Column::text('codigo_articulo', 50, required: true),   // BEAS_APL.ItemCode
                Column::integer('operacion', required: true),          // BEAS_APL.POS_ID
                Column::text('area'),                                  // BEAS_APLATZ.GRUPPE
                Column::text('puesto'),                                // BEAS_APLATZ.BEZ
                Column::quantity('tiempo'),                            // BEAS_APL.TEAPLATZ, for cantidad_base
                Column::quantity('cantidad_base'),                     // BEAS_APL.MENGE_JE
                Column::quantity('factor_merma'),                      // BEAS_APL.AUSSCHUSSFAKTOR
            ],
            Part::StandardCosts => [
                Column::text('codigo_articulo', 50, required: true),   // BEAS_FTPOS.ItemCode
                Column::text('articulo'),                              // MAX(ItemName)
                Column::text('familia', required: true),               // U_GSP_FAMILIA
                Column::integer('posiciones', required: true),         // COUNT(*)
                Column::quantity('cantidad', required: true),          // SUM(MENGE)
                Column::decimal('material_soll'),                      // SUM(MATERIAL_GK_SOLL)
                Column::decimal('fabricacion_soll'),                   // SUM(FERTIGUNG_GK_SOLL)
                Column::decimal('total_soll'),                         // SUM(SELBSTKOSTEN_GK_SOLL)
                Column::decimal('total_ist'),                          // SUM(SELBSTKOSTEN_GK_IST)
            ],
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
            // CntctPrsn: the name of the main contact, not its id (it matches
            // contactos.nombre). Omittable until the robot sends it (section 4.2).
            Column::text('contacto_principal', omittable: true),
        ];
    }

    /**
     * Where a PRODUCCION plant report or cost fact happened: the work center
     * group, the product line by the query's two-step rule, the business line
     * and the stage (contract section 12.2). In the material costs the area
     * is "Material comprado (sin area)" or "Material intermedio (sin area)".
     *
     * @return list<Column>
     */
    private static function productionArea(): array
    {
        return [
            Column::text('area', required: true),                      // BEAS_APLATZ.GRUPPE
            Column::text('linea_producto', required: true),            // the board's "Linea"
            Column::text('linea_negocio', required: true),             // OITB.ItmsGrpNam, "Sin grupo"
            Column::text('etapa', required: true),                     // BEAS_FTPOS.GRUPPE, "Sin etapa"
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
     * quantity, cost, total, VAT and gross profit; unit prices and costs come
     * unsigned.
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
            // INV1/RIN1.GrssProfit. A header may leave it out until the robot sends it (section 4.2).
            Column::decimal('ganancia_bruta', omittable: true),
            Column::text('moneda', 10),
            Column::quantity('trm'),
            Column::text('comentarios'),
            // Weight of the line ("Tot KG" of AnálisisVentas-1), negative on credit
            // notes. Omittable until the robot sends it (contract section 4.2).
            Column::quantity('kilos', omittable: true),
            // Code of the shipping address (OINV/ORIN.ShipToCode); in SDC, the
            // distribution centre. Omittable until the robot sends it (section 4.2).
            Column::text('codigo_envio', 50, omittable: true),
        ];
    }

    /**
     * One open customer order line (contract section 11.2), in contract
     * order. Quantities are in sales units; the pending total and gross
     * profit are in pesos and 0 on a tax-only line.
     *
     * @return list<Column>
     */
    private static function orders(): array
    {
        return [
            Column::integer('doc_entry', required: true),              // ORDR.DocEntry
            Column::integer('numero_pedido', required: true),          // ORDR.DocNum
            Column::integer('linea', required: true),                  // RDR1.LineNum
            Column::date('fecha_pedido', required: true),              // ORDR.DocDate
            Column::date('fecha_compromiso', required: true),          // ORDR.DocDueDate
            Column::date('fecha_entrega_linea'),                       // RDR1.ShipDate
            Column::integer('dias', required: true),                   // DocDate to today
            Column::text('rango', 20, required: true, values: self::ORDER_RANGES), // by dias
            Column::integer('dias_atraso', required: true),            // DocDueDate to today, negative until due
            Column::integer('slp_code', required: true),               // ORDR.SlpCode, -1 without one
            Column::text('vendedor'),                                  // OSLP.SlpName
            Column::text('canal'),                                     // OCRG.GroupName of the customer
            Column::text('codigo_cliente', 50, required: true),        // ORDR.CardCode
            Column::text('cliente'),                                   // ORDR.CardName
            Column::text('nit', 50),                                   // OCRD.LicTradNum
            Column::text('ciudad'),                                    // OCRD.City
            Column::text('id_pedido_app'),                             // ORDR.U_SGX_IdPedidoApp, only SGX
            Column::text('oc_cliente'),                                // ORDR.NumAtCard
            Column::text('direccion_envio'),                           // ORDR.Address2
            Column::text('comentarios'),                               // ORDR.Comments
            Column::text('codigo_articulo', 50, required: true),       // RDR1.ItemCode
            Column::text('descripcion'),                               // RDR1.Dscription
            Column::text('linea_articulo'),                            // OITB.ItmsGrpNam
            Column::text('familia'),                                   // OITM.U_GSP_FAMILIA, only SGX
            Column::text('marca'),                                     // OMRC.FirmName
            Column::text('bodega', 50),                                // RDR1.WhsCode
            Column::text('unidad', 100),                               // RDR1.unitMsr
            Column::quantity('cantidad_pedida', required: true),       // RDR1.Quantity
            Column::quantity('cantidad_pendiente', required: true),    // RDR1.OpenCreQty
            Column::decimal('precio_lista'),                           // RDR1.PriceBefDi, line currency
            Column::decimal('precio_unitario'),                        // RDR1.Price, line currency
            Column::quantity('descuento_documento'),                   // ORDR.DiscPrcnt
            Column::decimal('total_pendiente', required: true),        // LineTotal share of OpenCreQty, less DiscPrcnt
            Column::decimal('ganancia_bruta_pendiente'),               // GrssProfit share of OpenCreQty
            Column::text('moneda', 10),                                // ORDR.DocCur
            Column::quantity('trm'),                                   // ORDR.DocRate
        ];
    }
}
