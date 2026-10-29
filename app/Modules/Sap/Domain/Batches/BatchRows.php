<?php

namespace App\Modules\Sap\Domain\Batches;

use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Domain\Columns\Column;
use App\Modules\Sap\Domain\Columns\ColumnType;
use App\Modules\Sap\Domain\Values\SapTime;

/**
 * Checks and normalizes the rows of a batch (docs/contrato-robot.md,
 * section 4.2). Columns may come in any order but must be exactly the
 * part's, without repeats; rows come back as lists in the part's column
 * order, with text trimmed, times in the app timezone and amounts as text.
 */
final class BatchRows
{
    /** Longest text the contract allows, in characters. */
    private const MAX_TEXT = 4000;

    /** The contract reports at most this many errors. */
    private const MAX_ERRORS = 50;

    private const AMOUNT = '/^-?\d{1,17}(\.\d{1,2})?$/';

    /** Fits decimal(19,6): 13 integer digits and up to 6 decimals. */
    private const QUANTITY = '/^-?\d{1,13}(\.\d{1,6})?$/';

    /**
     * @return array{rows: list<list<mixed>>, errors: array<string, string>}
     */
    public static function check(Part $part, mixed $columns, mixed $rows): array
    {
        $expected = $part->columns();
        $columnError = self::columnError($expected, $columns);

        if ($columnError !== null) {
            return ['rows' => [], 'errors' => ['columns' => $columnError]];
        }

        /** @var list<string> $columns */
        $positions = array_flip($columns);
        $keys = array_flip($part->key());
        $normalized = [];
        $errors = [];

        foreach (is_array($rows) ? array_values($rows) : [] as $index => $row) {
            if (! is_array($row) || ! array_is_list($row) || count($row) !== count($columns)) {
                $errors["rows.{$index}"] = 'La fila debe traer un valor por columna.';
            } else {
                $values = [];

                foreach ($expected as $name => $column) {
                    [$value, $error] = self::value($column, $row[$positions[$name]], isset($keys[$name]));
                    $values[] = $value;

                    if ($error !== null) {
                        $errors["rows.{$index}.{$name}"] = $error;
                    }
                }

                $normalized[] = $values;
            }

            if (count($errors) >= self::MAX_ERRORS) {
                break;
            }
        }

        return ['rows' => $errors === [] ? $normalized : [], 'errors' => array_slice($errors, 0, self::MAX_ERRORS, true)];
    }

    /**
     * Identifies the key of a normalized row inside its part. Exact and
     * case-sensitive, like the SAP keys and the utf8mb4_bin key columns.
     *
     * @param  list<mixed>  $row
     */
    public static function keyHash(Part $part, array $row): string
    {
        $positions = array_flip(array_keys($part->columns()));

        return hash('sha256', (string) json_encode(array_map(fn (string $key): mixed => $row[$positions[$key]], $part->key())));
    }

    /**
     * @param  array<string, Column>  $expected
     */
    private static function columnError(array $expected, mixed $columns): ?string
    {
        if (! is_array($columns) || ! array_is_list($columns) || array_filter($columns, 'is_string') !== $columns) {
            return 'Debe ser la lista de nombres de columnas.';
        }

        $repeated = array_keys(array_filter(array_count_values($columns), fn (int $count): bool => $count > 1));
        $missing = array_diff(array_keys($expected), $columns);
        $unknown = array_diff($columns, array_keys($expected));

        $problems = array_filter([
            $missing === [] ? null : 'Faltan columnas: '.implode(', ', $missing).'.',
            $unknown === [] ? null : 'Columnas desconocidas: '.implode(', ', $unknown).'.',
            $repeated === [] ? null : 'Columnas repetidas: '.implode(', ', $repeated).'.',
        ]);

        return $problems === [] ? null : implode(' ', $problems);
    }

    /**
     * The normalized value and the error, if any.
     *
     * @return array{0: mixed, 1: string|null}
     */
    private static function value(Column $column, mixed $value, bool $isKey): array
    {
        if (is_string($value) && $column->type === ColumnType::Text) {
            $value = trim($value);
        }

        if ($value === null || $value === '') {
            return [null, $column->required ? 'Es obligatoria.' : null];
        }

        return match ($column->type) {
            ColumnType::Text => self::text($column, $value, $isKey),
            ColumnType::Integer => match (true) {
                ! is_int($value) || $value < -2147483648 || $value > 2147483647 => [null, 'Debe ser un entero.'],
                $column->min !== null && $value < $column->min => [null, "Debe ser mayor o igual a {$column->min}."],
                default => [$value, null],
            },
            ColumnType::Decimal => is_string($value) && preg_match(self::AMOUNT, $value) === 1
                ? [$value, null]
                : [null, 'Debe ser un monto como texto, con punto y hasta 2 decimales.'],
            ColumnType::Quantity => is_string($value) && preg_match(self::QUANTITY, $value) === 1
                ? [$value, null]
                : [null, 'Debe ser una cantidad como texto, con punto y hasta 6 decimales.'],
            ColumnType::Boolean => is_bool($value) ? [$value, null] : [null, 'Debe ser true o false.'],
            ColumnType::Date => SapTime::isDate($value) ? [$value, null] : [null, 'Debe ser una fecha AAAA-MM-DD.'],
            ColumnType::DateTime => ($time = SapTime::parse($value)) !== null
                ? [$time->format('Y-m-d H:i:s'), null]
                : [null, 'Debe ser una hora ISO 8601 con zona.'],
        };
    }

    /**
     * Text longer than its column is cut, except a key, which would stop
     * being unique; anything over the contract's 4,000 characters is refused.
     *
     * @return array{0: string|null, 1: string|null}
     */
    private static function text(Column $column, mixed $value, bool $isKey): array
    {
        if (! is_string($value)) {
            return [null, 'Debe ser texto.'];
        }

        $length = mb_strlen($value);
        $max = $column->length ?? 255;

        return match (true) {
            $length > self::MAX_TEXT => [null, 'Pasa de 4.000 caracteres.'],
            $length > $max && $isKey => [null, "Pasa de {$max} caracteres."],
            default => [mb_substr($value, 0, $max), null],
        };
    }
}
