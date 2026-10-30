<?php

namespace App\Modules\Sap\Domain\Columns;

/**
 * How a value travels in a batch (docs/contrato-robot.md, section 4.2).
 */
enum ColumnType: string
{
    /** A string, trimmed and cut to the column length. */
    case Text = 'text';

    /** A JSON integer. */
    case Integer = 'integer';

    /** An amount as decimal text with a dot and up to 2 decimals: "1234567.89". */
    case Decimal = 'decimal';

    /** A quantity or rate (only VENTAS) as decimal text with a dot and up to 6 decimals: "2.500000". */
    case Quantity = 'quantity';

    /** JSON true or false. */
    case Boolean = 'boolean';

    /** "YYYY-MM-DD". */
    case Date = 'date';

    /** ISO 8601 with offset: "2026-10-23T10:42:05-05:00". */
    case DateTime = 'datetime';
}
