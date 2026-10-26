<?php

namespace App\Modules\Sap\Contracts\Enums;

use App\Modules\Sap\Domain\Columns\Column;
use App\Modules\Sap\Domain\Columns\PartColumns;

/**
 * A logical table inside a dataset (docs/contrato-robot.md, sections 1, 5
 * and 6). The value is the contract name, which is also the MySQL table;
 * apps read it through the view v_<value>.
 */
enum Part: string
{
    case Customers = 'clientes';
    case Suppliers = 'proveedores';
    case Addresses = 'direcciones';
    case Contacts = 'contactos';
    case Items = 'articulos';
    case ItemGroups = 'grupos_articulos';
    case Brands = 'marcas';
    case Prices = 'precios';
    case SalesPeople = 'vendedores';
    case CustomerGroups = 'grupos_clientes';
    case PaymentTerms = 'condiciones_pago';
    case Municipalities = 'municipios';
    case Receivables = 'cartera';

    /**
     * The parts of a dataset, in contract order.
     *
     * @return list<self>
     */
    public static function forDataset(Dataset $dataset): array
    {
        return array_values(array_filter(self::cases(), fn (self $part): bool => $part->dataset() === $dataset));
    }

    public function dataset(): Dataset
    {
        return $this === self::Receivables ? Dataset::Cartera : Dataset::Maestros;
    }

    public function table(): string
    {
        return $this->value;
    }

    /**
     * The stable view the apps read instead of the table.
     */
    public function view(): string
    {
        return 'v_'.$this->value;
    }

    /**
     * The columns that identify a row inside a company. CARTERA has none:
     * each close replaces the whole company (contract section 6).
     *
     * @return list<string>
     */
    public function key(): array
    {
        return match ($this) {
            self::Addresses => ['codigo_socio', 'tipo', 'nombre'],
            self::Contacts => ['contacto_id'],
            self::Prices => ['articulo_codigo'],
            self::Receivables => [],
            default => ['codigo'],
        };
    }

    /**
     * The columns the robot sends for the part, in contract order.
     *
     * @return array<string, Column>
     */
    public function columns(): array
    {
        return PartColumns::for($this);
    }

    /**
     * Whether the part carries actualizado_en_sap, so a request can bring
     * only what changed since the newest one in MySQL (contract section 5.1).
     */
    public function tracksSapUpdates(): bool
    {
        return in_array($this, [self::Customers, self::Suppliers, self::Items], true);
    }
}
