<?php

namespace App\Modules\Panel\Support;

use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\RequestScope;
use Illuminate\Support\Str;

/**
 * What the «Actualizar datos» form can ask for: each dataset whole, plus
 * each scope that RequestScope::forDataset allows for it. The value is
 * "MAESTROS" or "MAESTROS:clientes"; everything comes from the Sap enums,
 * so a new dataset (VENTAS) shows as one more option with no change here.
 */
final class UpdateOptions
{
    private const string SEPARATOR = ':';

    /**
     * Every option, dataset by dataset, the whole dataset first.
     *
     * @return list<array{value: string, label: string, dataset: Dataset, scope: RequestScope|null}>
     */
    public static function all(): array
    {
        $options = [];

        foreach (Dataset::cases() as $dataset) {
            foreach ([null, ...RequestScope::forDataset($dataset)] as $scope) {
                $options[] = [
                    'value' => $scope === null ? $dataset->value : $dataset->value.self::SEPARATOR.$scope->value,
                    'label' => __('panel::actualizar.opcion', [
                        'conjunto' => Labels::dataset($dataset->value),
                        'parte' => $scope === null ? __('panel::actualizar.todo') : Str::lcfirst(Labels::scope($scope->value)),
                    ]),
                    'dataset' => $dataset,
                    'scope' => $scope,
                ];
            }
        }

        return $options;
    }

    /**
     * The values a form may send.
     *
     * @return list<string>
     */
    public static function values(): array
    {
        return array_column(self::all(), 'value');
    }

    /**
     * The dataset and scope of a value, or null when it is not an option
     * (say a scope that does not belong to the dataset).
     *
     * @return array{dataset: Dataset, scope: RequestScope|null}|null
     */
    public static function find(string $value): ?array
    {
        foreach (self::all() as $option) {
            if ($option['value'] === $value) {
                return ['dataset' => $option['dataset'], 'scope' => $option['scope']];
            }
        }

        return null;
    }
}
