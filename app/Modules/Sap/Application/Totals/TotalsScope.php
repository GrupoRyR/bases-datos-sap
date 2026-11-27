<?php

namespace App\Modules\Sap\Application\Totals;

use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Domain\Values\SapTime;

/**
 * What a total or a comparison is about (docs/contrato-robot.md, sections
 * 13.2 and 13.3): a dataset with totals, a company and, only in VENTAS, an
 * optional range of posting dates, both ends included. A null desde or
 * hasta is the same as leaving it out.
 */
final readonly class TotalsScope
{
    /** The datasets with totals, for now. */
    public const DATASETS = [Dataset::Maestros, Dataset::Cartera, Dataset::Ventas];

    public function __construct(
        public Dataset $dataset,
        public Company $company,
        public ?string $from = null,
        public ?string $until = null,
    ) {}

    /**
     * The scope of the input, or null with the reasons added to $errors.
     *
     * @param  array<string, mixed>  $input
     * @param  array<string, string>  $errors  Field => message.
     */
    public static function fromInput(array $input, array &$errors): ?self
    {
        $dataset = Dataset::tryFrom(is_string($input['conjunto'] ?? null) ? $input['conjunto'] : '');
        $company = Company::tryFrom(is_string($input['empresa'] ?? null) ? $input['empresa'] : '');

        if ($dataset === null || ! in_array($dataset, self::DATASETS, true)) {
            $errors['conjunto'] = 'Conjunto sin totales: solo MAESTROS, CARTERA o VENTAS.';
            $dataset = null;
        }

        if ($company === null) {
            $errors['empresa'] = 'Empresa desconocida: solo SGX o SDC.';
        }

        $from = self::date($input['desde'] ?? null, 'desde', $dataset, $errors);
        $until = self::date($input['hasta'] ?? null, 'hasta', $dataset, $errors);

        if ($from !== null && $until !== null && $from > $until) {
            $errors['hasta'] = 'Debe ser igual o posterior a desde.';
        }

        if ($errors !== [] || $dataset === null || $company === null) {
            return null;
        }

        return new self($dataset, $company, $from, $until);
    }

    /**
     * A desde or hasta: a date only in VENTAS, null when it does not come.
     *
     * @param  array<string, string>  $errors
     */
    private static function date(mixed $value, string $field, ?Dataset $dataset, array &$errors): ?string
    {
        if ($value === null || $dataset === null) {
            return null;
        }

        if ($dataset !== Dataset::Ventas) {
            $errors[$field] = "Solo VENTAS lleva {$field}.";

            return null;
        }

        if (! is_string($value) || ! SapTime::isDate($value)) {
            $errors[$field] = 'Debe ser una fecha AAAA-MM-DD.';

            return null;
        }

        return $value;
    }
}
