<?php

namespace App\Modules\Sap\Application\Totals;

use App\Modules\Sap\Domain\Values\SapTime;
use App\Modules\Sap\Http\Exceptions\RobotRequestRejected;
use App\Modules\Sap\Models\RobotComparison;

/**
 * Stores what the robot reports after comparing its totals of SAP with
 * those of MySQL (docs/contrato-robot.md, section 13.3). It is kept for the
 * coordinator and the panel and never applied to the data.
 */
final class StoreComparison
{
    public const MAX_DIFFERENCES = 500;

    /** The longest text of each field of a difference. */
    private const LENGTHS = ['clave' => 20, 'campo' => 40, 'sap' => 40, 'mysql' => 40];

    /** The fields of a difference that may be null. */
    private const NULLABLE = ['sap', 'mysql'];

    /** @var array<string, string> */
    private array $errors = [];

    /**
     * @param  array<string, mixed>  $input
     */
    public function handle(array $input, string $robotKey): RobotComparison
    {
        $this->errors = [];

        $scope = TotalsScope::fromInput($input, $this->errors);
        $comparedAt = SapTime::parse($input['comparada_en'] ?? null);
        $matches = $input['cuadra'] ?? null;
        $differences = $this->differences($input['diferencias'] ?? null);

        if ($comparedAt === null) {
            $this->errors['comparada_en'] = 'Debe ser una hora ISO 8601 con zona.';
        }

        if (! is_bool($matches)) {
            $this->errors['cuadra'] = 'Debe ser true o false.';
        } elseif ($differences !== null && $matches && $differences !== []) {
            $this->errors['diferencias'] ??= 'Si cuadra, no lleva diferencias.';
        } elseif ($differences !== null && ! $matches && $differences === []) {
            $this->errors['diferencias'] ??= 'Si no cuadra, lleva al menos una diferencia.';
        }

        if ($this->errors !== [] || $scope === null || $comparedAt === null || ! is_bool($matches) || $differences === null) {
            throw RobotRequestRejected::invalid('La comparación no cumple el contrato.', $this->errors);
        }

        return RobotComparison::create([
            'conjunto' => $scope->dataset,
            'empresa' => $scope->company,
            'desde' => $scope->from,
            'hasta' => $scope->until,
            'cuadra' => $matches,
            'diferencias' => $differences,
            'comparada_en' => $comparedAt,
            'robot_key' => $robotKey,
        ]);
    }

    /**
     * The differences as a list of {clave, campo, sap, mysql}, or null with
     * the reasons in errors.
     *
     * @return list<array{clave: string, campo: string, sap: string|null, mysql: string|null}>|null
     */
    private function differences(mixed $differences): ?array
    {
        if (! is_array($differences) || ! array_is_list($differences)) {
            $this->errors['diferencias'] = 'Debe ser una lista.';

            return null;
        }

        if (count($differences) > self::MAX_DIFFERENCES) {
            $this->errors['diferencias'] = 'Lleva como máximo '.self::MAX_DIFFERENCES.' diferencias.';

            return null;
        }

        $clean = [];

        foreach ($differences as $i => $difference) {
            $item = $this->difference($difference, "diferencias.{$i}");

            if ($item !== null) {
                $clean[] = $item;
            }
        }

        return count($clean) === count($differences) ? $clean : null;
    }

    /**
     * @return array{clave: string, campo: string, sap: string|null, mysql: string|null}|null
     */
    private function difference(mixed $difference, string $path): ?array
    {
        // Any other key (a list's numeric ones too) is refused.
        if (! is_array($difference) || array_diff_key($difference, self::LENGTHS) !== []) {
            $this->errors[$path] = 'Debe ser un objeto con clave, campo, sap y mysql.';

            return null;
        }

        $key = $this->text($difference, 'clave', $path);
        $field = $this->text($difference, 'campo', $path);
        $sap = $this->text($difference, 'sap', $path);
        $mysql = $this->text($difference, 'mysql', $path);

        if (! is_string($key) || ! is_string($field) || $sap === false || $mysql === false) {
            return null;
        }

        return ['clave' => $key, 'campo' => $field, 'sap' => $sap, 'mysql' => $mysql];
    }

    /**
     * A text field of a difference, null where null is allowed, or false
     * with the reason in errors. The field must come, even when null.
     *
     * @param  array<mixed>  $difference
     */
    private function text(array $difference, string $field, string $path): string|false|null
    {
        $length = self::LENGTHS[$field];
        $nullable = in_array($field, self::NULLABLE, true);
        $value = $difference[$field] ?? null;

        if (! array_key_exists($field, $difference)) {
            $this->errors["{$path}.{$field}"] = 'Falta.';

            return false;
        }

        if ($value === null && $nullable) {
            return null;
        }

        if (! is_string($value) || mb_strlen($value) > $length || ($value === '' && ! $nullable)) {
            $this->errors["{$path}.{$field}"] = $nullable
                ? "Debe ser texto de hasta {$length} caracteres o null."
                : "Debe ser texto de 1 a {$length} caracteres.";

            return false;
        }

        return $value;
    }
}
