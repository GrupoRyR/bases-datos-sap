<?php

namespace App\Modules\Sap\Contracts\Enums;

/**
 * The part of MAESTROS a request can ask for (docs/contrato-robot.md,
 * section 7.1). A request without scope asks for the whole dataset; CARTERA
 * is always asked whole.
 */
enum RequestScope: string
{
    case Customers = 'clientes';
    case Suppliers = 'proveedores';
    case Items = 'articulos';
    case Prices = 'precios';
    case SalesPeople = 'vendedores';
    case Catalogs = 'catalogos';

    /**
     * The scopes a request of the dataset may name.
     *
     * @return list<self>
     */
    public static function forDataset(Dataset $dataset): array
    {
        return $dataset === Dataset::Maestros ? self::cases() : [];
    }

    /**
     * The parts the run brings for a request of the dataset and scope.
     *
     * @return list<Part>
     */
    public static function partsFor(Dataset $dataset, ?self $scope): array
    {
        return $scope?->parts() ?? Part::forDataset($dataset);
    }

    /**
     * @return list<Part>
     */
    public function parts(): array
    {
        return match ($this) {
            self::Customers => [Part::Customers, Part::Addresses, Part::Contacts],
            self::Suppliers => [Part::Suppliers, Part::Addresses, Part::Contacts],
            self::Items => [Part::Items, Part::ItemGroups, Part::Brands],
            self::Prices => [Part::Prices],
            self::SalesPeople => [Part::SalesPeople],
            self::Catalogs => [Part::CustomerGroups, Part::PaymentTerms, Part::Municipalities],
        };
    }
}
