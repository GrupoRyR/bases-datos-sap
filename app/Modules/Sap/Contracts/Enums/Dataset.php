<?php

namespace App\Modules\Sap\Contracts\Enums;

/**
 * A group of SAP data with its own MySQL tables, each on the database of its
 * connection (docs/contrato-robot.md, section 1). Only these datasets exist; archive-only tables never reach
 * the API (docs/plan-bases-sap.md, section 5).
 */
enum Dataset: string
{
    /** Customers, suppliers, items and catalogs, in maestros_sap. */
    case Maestros = 'MAESTROS';

    /** Open invoices and balances, plus one photo per day, in cartera_sap. */
    case Cartera = 'CARTERA';

    /** Invoice and credit note lines, replaced only inside a window, in ventas_sap. */
    case Ventas = 'VENTAS';

    /** Open customer order lines, replaced whole per company, in ventas_sap next to VENTAS. */
    case Pedidos = 'PEDIDOS';

    /** Segurex production (BEAS): movement replaced inside a window, masters whole, in ventas_sap. */
    case Produccion = 'PRODUCCION';

    /**
     * The database connection that holds the tables of the dataset
     * (config/database.php).
     */
    public function connection(): string
    {
        return match ($this) {
            self::Maestros => 'maestros',
            self::Cartera => 'cartera',
            self::Ventas, self::Pedidos, self::Produccion => 'ventas',
        };
    }

    /**
     * The companies that have the dataset. The BEAS production tables are
     * Segurex only, so PRODUCCION never runs or is asked for Derivados
     * (contract section 12).
     *
     * @return list<Company>
     */
    public function companies(): array
    {
        return $this === self::Produccion ? [Company::Sgx] : Company::cases();
    }
}
