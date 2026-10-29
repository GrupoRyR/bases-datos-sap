<?php

namespace App\Modules\Panel\Http\Controllers;

use App\Modules\Panel\Support\Formats;
use App\Modules\Panel\Support\Labels;
use App\Modules\Sap\Contracts\Data\DatasetStatusData;
use App\Modules\Sap\Contracts\Data\RunSummaryData;
use App\Modules\Sap\Contracts\Data\StabilityData;
use App\Modules\Sap\Contracts\DatasetStatuses;
use App\Modules\Sap\Contracts\Stability;
use Illuminate\Contracts\View\View;

/**
 * GET /panel (panel.estado): the stability counter of plan section 6 and,
 * per company, how each dataset stands. It walks whatever Sap returns, so a
 * new company, dataset or part shows with no change here. The view gets
 * plain, already formatted data.
 */
final class StatusController
{
    public function __invoke(DatasetStatuses $statuses, Stability $stability): View
    {
        return view('panel::estado', [
            'stability' => $this->stability($stability->current()),
            'companies' => $this->companies($statuses->all()),
        ]);
    }

    /**
     * @return array{stableDays: int, targetDays: int, days: list<array{iso: string, date: string, state: string, problems: list<string>}>}
     */
    private function stability(StabilityData $stability): array
    {
        $days = [];

        foreach ($stability->days as $day) {
            // Sap marks today in progress while it only lacks what has not run yet.
            $state = match (true) {
                $day->stable => 'estable',
                $day->inProgress => 'en_curso',
                default => 'con_fallas',
            };

            $days[] = [
                'iso' => Formats::isoDate($day->date),
                'date' => Formats::shortDate($day->date),
                'state' => $state,
                'problems' => $day->problems,
            ];
        }

        return [
            'stableDays' => $stability->stableDays,
            'targetDays' => $stability->targetDays,
            'days' => $days,
        ];
    }

    /**
     * Statuses grouped by company, in the order Sap returns them.
     *
     * @param  list<DatasetStatusData>  $statuses
     * @return list<array{label: string, datasets: list<array<string, mixed>>}>
     */
    private function companies(array $statuses): array
    {
        $companies = [];

        foreach ($statuses as $status) {
            $code = $status->company->value;

            $companies[$code] ??= ['label' => Labels::company($code), 'datasets' => []];
            $companies[$code]['datasets'][] = [
                'label' => Labels::dataset($status->dataset->value),
                'appliedAt' => $status->lastAppliedAt === null ? null : [
                    'iso' => Formats::isoDateTime($status->lastAppliedAt),
                    'text' => Formats::dateTime($status->lastAppliedAt),
                ],
                'rows' => array_map(
                    fn (string $part, int $rows): array => ['label' => Labels::part($part), 'count' => Formats::number($rows)],
                    array_keys($status->rows),
                    array_values($status->rows),
                ),
                'lastRun' => $status->lastRun === null ? null : $this->run($status->lastRun),
            ];
        }

        return array_values($companies);
    }

    /**
     * @return array<string, mixed>
     */
    private function run(RunSummaryData $run): array
    {
        return [
            'type' => Labels::runType($run->type),
            'state' => Labels::runState($run->state),
            'tone' => Labels::runStateTone($run->state),
            'startedAt' => ['iso' => Formats::isoDateTime($run->startedAt), 'text' => Formats::dateTime($run->startedAt)],
            'finishedAt' => $run->finishedAt === null ? null : [
                'iso' => Formats::isoDateTime($run->finishedAt),
                'text' => Formats::dateTime($run->finishedAt),
            ],
            // By contract the error carries no secrets; only a failed or
            // expired run explains itself.
            'error' => in_array($run->state, ['fallida', 'vencida'], true) ? $run->error : null,
        ];
    }
}
