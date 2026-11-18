<?php

namespace App\Modules\Sap\Contracts\Enums;

use App\Modules\Sap\Domain\Columns\Column;
use App\Modules\Sap\Domain\Columns\PartColumns;

/**
 * A logical table inside a dataset (docs/contrato-robot.md, sections 1, 5,
 * 6, 10, 11 and 12). The value is the contract name, which is also the MySQL table;
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
    case Sales = 'ventas';
    case Orders = 'pedidos';
    case ProductionFinished = 'produccion_terminado';
    case PlantLoad = 'produccion_carga_planta';
    case ProductionCosts = 'produccion_costos';
    case BillOfMaterials = 'produccion_despiece';
    case Routings = 'produccion_rutas';
    case StandardCosts = 'produccion_costeo_teorico';

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
        return match ($this) {
            self::Receivables => Dataset::Cartera,
            self::Sales => Dataset::Ventas,
            self::Orders => Dataset::Pedidos,
            self::ProductionFinished, self::PlantLoad, self::ProductionCosts,
            self::BillOfMaterials, self::Routings, self::StandardCosts => Dataset::Produccion,
            default => Dataset::Maestros,
        };
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
     * each close replaces the whole company (contract section 6). A VENTAS
     * line is its document type, document and line (contract section 10); a
     * PEDIDOS line, its order and line (contract section 11.2). In PRODUCCION
     * only the finished goods (entry and line) and the standard costs (item)
     * have one; plant reports and cost facts repeat legitimately, and the bill
     * of materials and routings wait for SAP to confirm theirs (section 12.2).
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
            self::Sales => ['tipo_objeto', 'doc_entry', 'linea'],
            self::Orders, self::ProductionFinished => ['doc_entry', 'linea'],
            self::StandardCosts => ['codigo_articulo'],
            self::PlantLoad, self::ProductionCosts, self::BillOfMaterials, self::Routings => [],
            default => ['codigo'],
        };
    }

    /**
     * The date column a window is measured on, or null for a part without
     * one. Its batches refuse rows before the run's ventana_desde, its close
     * replaces only the rows from that day on and its count covers just them
     * (contract sections 10.1 and 12.3).
     */
    public function windowColumn(): ?string
    {
        return match ($this) {
            self::Sales => 'fecha_contabilizacion',
            self::ProductionFinished, self::PlantLoad, self::ProductionCosts => 'fecha',
            default => null,
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
        return isset($this->columns()['actualizado_en_sap']);
    }
}
