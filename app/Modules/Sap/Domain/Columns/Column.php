<?php

namespace App\Modules\Sap\Domain\Columns;

/**
 * One column of a part as the robot sends it (docs/contrato-robot.md,
 * sections 5.2, 6 and 10). Required columns are the bold ones of the contract
 * and the key; they can never arrive null or empty.
 */
final readonly class Column
{
    private function __construct(
        public string $name,
        public ColumnType $type,
        public bool $required,
        // The maximum length of a text column, in characters.
        public ?int $length = null,
        // The minimum value of an integer column.
        public ?int $min = null,
    ) {}

    public static function text(string $name, int $length = 255, bool $required = false): self
    {
        return new self($name, ColumnType::Text, $required, length: $length);
    }

    public static function integer(string $name, bool $required = false, ?int $min = null): self
    {
        return new self($name, ColumnType::Integer, $required, min: $min);
    }

    public static function decimal(string $name, bool $required = false): self
    {
        return new self($name, ColumnType::Decimal, $required);
    }

    public static function quantity(string $name, bool $required = false): self
    {
        return new self($name, ColumnType::Quantity, $required);
    }

    public static function boolean(string $name, bool $required = false): self
    {
        return new self($name, ColumnType::Boolean, $required);
    }

    public static function date(string $name, bool $required = false): self
    {
        return new self($name, ColumnType::Date, $required);
    }

    public static function dateTime(string $name, bool $required = false): self
    {
        return new self($name, ColumnType::DateTime, $required);
    }
}
