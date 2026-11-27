<?php

namespace App\Modules\Sap\Application\Totals;

use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\Part;
use Carbon\CarbonImmutable;
use Illuminate\Database\Connection;
use Illuminate\Support\Facades\DB;
use LogicException;
use stdClass;

/**
 * The totals the robot compares with SAP (docs/contrato-robot.md, section
 * 13.2). Read only. Sums are exact: on MySQL, SUM over the DECIMAL columns;
 * on any other driver (SQLite in tests, which keeps decimals as REAL), SUM
 * of each value scaled to an integer of its decimals. Either way the result
 * goes through bcmath as text, never through a PHP float.
 */
final class ComputeTotals
{
    /** The decimals of an amount and of a quantity (contract section 4.2). */
    private const AMOUNT = 2;

    private const QUANTITY = 6;

    /**
     * @return array{conjunto: string, empresa: string, grupos: list<array{clave: string, filas: int, sumas: object, nulos: object}>}
     */
    public function handle(TotalsScope $scope): array
    {
        return [
            'conjunto' => $scope->dataset->value,
            'empresa' => $scope->company->value,
            'grupos' => match ($scope->dataset) {
                Dataset::Ventas => $this->sales($scope),
                Dataset::Cartera => $this->receivables($scope->company),
                default => $this->masters($scope->company),
            },
        ];
    }

    /**
     * One group per posting month with lines, ascending. The month is the
     * first seven characters of the date, the same on MySQL and SQLite.
     *
     * @return list<array{clave: string, filas: int, sumas: object, nulos: object}>
     */
    private function sales(TotalsScope $scope): array
    {
        $db = DB::connection(Dataset::Ventas->connection());
        $month = 'SUBSTR(fecha_contabilizacion, 1, 7)';

        $query = $db->table(Part::Sales->table())
            ->where('empresa', $scope->company->value)
            ->selectRaw("{$month} AS clave")
            ->selectRaw('COUNT(*) AS filas')
            ->selectRaw($this->sumOf($db, 'total', self::AMOUNT).' AS suma_total')
            ->selectRaw($this->sumOf($db, 'cantidad', self::QUANTITY).' AS suma_cantidad')
            ->selectRaw('SUM(CASE WHEN kilos IS NULL THEN 1 ELSE 0 END) AS nulos_kilos')
            ->selectRaw('SUM(CASE WHEN codigo_envio IS NULL THEN 1 ELSE 0 END) AS nulos_codigo_envio')
            ->groupByRaw($month)
            ->orderByRaw($month);

        if ($scope->from !== null) {
            $query->where('fecha_contabilizacion', '>=', $scope->from);
        }

        // Before the next day, so a date stored with a time still counts.
        if ($scope->until !== null) {
            $query->where('fecha_contabilizacion', '<', CarbonImmutable::parse($scope->until)->addDay()->toDateString());
        }

        return $query->get()->map(fn (stdClass $row): array => [
            'clave' => (string) $row->clave,
            'filas' => (int) $row->filas,
            'sumas' => (object) [
                'total' => $this->exact($db, $row->suma_total, self::AMOUNT),
                'cantidad' => $this->exact($db, $row->suma_cantidad, self::QUANTITY),
            ],
            'nulos' => (object) [
                'kilos' => (int) $row->nulos_kilos,
                'codigo_envio' => (int) $row->nulos_codigo_envio,
            ],
        ])->values()->all();
    }

    /**
     * The current receivables of the company in one group, also when empty.
     *
     * @return list<array{clave: string, filas: int, sumas: object, nulos: object}>
     */
    private function receivables(Company $company): array
    {
        $db = DB::connection(Dataset::Cartera->connection());

        /** @var stdClass $row */
        $row = $db->table(Part::Receivables->table())
            ->where('empresa', $company->value)
            ->selectRaw('COUNT(*) AS filas')
            ->selectRaw($this->sumOf($db, 'saldo', self::AMOUNT).' AS suma_saldo')
            ->first();

        return [[
            'clave' => 'actual',
            'filas' => (int) $row->filas,
            'sumas' => (object) ['saldo' => $this->exact($db, $row->suma_saldo, self::AMOUNT)],
            'nulos' => (object) [],
        ]];
    }

    /**
     * The active rows of the company in every part, in contract order.
     *
     * @return list<array{clave: string, filas: int, sumas: object, nulos: object}>
     */
    private function masters(Company $company): array
    {
        $db = DB::connection(Dataset::Maestros->connection());

        return array_map(fn (Part $part): array => [
            'clave' => $part->value,
            'filas' => $db->table($part->table())->where('empresa', $company->value)->where('activo', true)->count(),
            'sumas' => (object) [],
            'nulos' => (object) [],
        ], Part::forDataset(Dataset::Maestros));
    }

    /**
     * The SQL of an exact sum of a decimal column with $scale decimals.
     */
    private function sumOf(Connection $db, string $column, int $scale): string
    {
        return $this->sumsDecimals($db)
            ? "SUM({$column})"
            : "SUM(CAST(ROUND({$column} * 1{$this->zeros($scale)}) AS INTEGER))";
    }

    /**
     * The sum as contract text: exactly $scale decimals, "-" when negative,
     * rounded half away from zero (stored values already have $scale
     * decimals, so it only pads). An empty sum is zero.
     */
    private function exact(Connection $db, mixed $sum, int $scale): string
    {
        if ($sum !== null && ! is_int($sum) && ! is_string($sum)) {
            throw new LogicException('An exact sum must come back as an integer or a decimal string.');
        }

        $value = (string) ($sum ?? '0');

        if (! $this->sumsDecimals($db)) {
            $value = bcdiv($value, '1'.$this->zeros($scale), $scale);
        }

        $half = '0.'.$this->zeros($scale).'5';
        $rounded = bcadd($value, str_starts_with($value, '-') ? '-'.$half : $half, $scale);

        return bccomp($rounded, '0', $scale) === 0 ? bcadd('0', '0', $scale) : $rounded;
    }

    /**
     * Whether the driver keeps DECIMAL columns exact and sums them so.
     */
    private function sumsDecimals(Connection $db): bool
    {
        return in_array($db->getDriverName(), ['mysql', 'mariadb'], true);
    }

    private function zeros(int $scale): string
    {
        return str_repeat('0', $scale);
    }
}
