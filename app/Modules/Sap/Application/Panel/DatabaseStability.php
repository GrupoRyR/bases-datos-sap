<?php

namespace App\Modules\Sap\Application\Panel;

use App\Modules\Sap\Contracts\Data\StabilityData;
use App\Modules\Sap\Contracts\Data\StabilityDayData;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\RequestState;
use App\Modules\Sap\Contracts\Stability;
use App\Modules\Sap\Domain\Runs\RunState;
use App\Modules\Sap\Domain\Runs\RunType;
use Carbon\CarbonImmutable;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\DB;
use stdClass;

/**
 * Computes the stability counter from robot_runs, daily_counts and
 * update_requests, three queries for the whole window. Times are stored in
 * the app timezone (Bogota), so the first ten characters of a stored time
 * are its Bogota day.
 */
final class DatabaseStability implements Stability
{
    /** A request is on time when it finished less than this after correr_desde. */
    private const ON_TIME_SECONDS = 600;

    public function current(): StabilityData
    {
        $today = CarbonImmutable::now((string) config('app.timezone'))->startOfDay();
        // One day more than the target: while today is in progress, the
        // streak may still reach the target counting from yesterday.
        $from = $today->subDays(self::TARGET_DAYS);
        $until = $today->addDay();
        $day = fn (stdClass $row, string $column): string => substr((string) $row->{$column}, 0, 10);

        $runs = DB::table('robot_runs')
            ->where('tipo', RunType::Full->value)
            ->where('extraida_en', '>=', $from->toDateTimeString())
            ->where('extraida_en', '<', $until->toDateTimeString())
            ->get(['empresa', 'conjunto', 'estado', 'extraida_en'])
            ->groupBy(fn (stdClass $run): string => $day($run, 'extraida_en'));

        $counts = DB::table('daily_counts')
            ->where('fecha', '>=', $from->toDateString())
            ->where('fecha', '<', $until->toDateString())
            ->orderBy('id')
            ->get(['fecha', 'empresa', 'conjunto', 'parte', 'cuadra'])
            ->groupBy(fn (stdClass $count): string => $day($count, 'fecha'));

        // Requests still waiting or being served are not judged yet.
        $requests = DB::table('update_requests')
            ->whereIn('estado', [RequestState::Done->value, RequestState::Failed->value, RequestState::Expired->value])
            ->where('correr_desde', '>=', $from->toDateTimeString())
            ->where('correr_desde', '<', $until->toDateTimeString())
            ->orderBy('correr_desde')
            ->orderBy('id')
            ->get(['id', 'estado', 'correr_desde', 'terminada_en'])
            ->groupBy(fn (stdClass $request): string => $day($request, 'correr_desde'));

        $days = [];

        for ($i = 0; $i <= self::TARGET_DAYS; $i++) {
            $date = $today->subDays($i);
            $key = $date->toDateString();
            $days[] = $this->day($date, $runs->get($key, collect()), $counts->get($key, collect()), $requests->get($key, collect()));
        }

        // Today is still running: unless it is stable or already failed for
        // good, it only lacks what has not run yet.
        $todayKey = $today->toDateString();
        $todayFailed = $this->failedForGood($runs->get($todayKey, collect()), $counts->get($todayKey, collect()), $requests->get($todayKey, collect()));

        if (! $days[0]->stable && ! $todayFailed) {
            $days[0] = new StabilityDayData(
                date: $days[0]->date,
                nightlyRunsOk: $days[0]->nightlyRunsOk,
                countsMatch: $days[0]->countsMatch,
                requestsOnTime: $days[0]->requestsOnTime,
                stable: false,
                problems: $days[0]->problems,
                inProgress: true,
            );
        }

        return new StabilityData(
            stableDays: min($this->streak($days), self::TARGET_DAYS),
            targetDays: self::TARGET_DAYS,
            days: array_slice($days, 0, self::TARGET_DAYS),
        );
    }

    /**
     * Stable days in a row from today back. A day in progress (today) is
     * skipped; any other unstable day ends the streak.
     *
     * @param  list<StabilityDayData>  $days  Today first.
     */
    private function streak(array $days): int
    {
        $streak = 0;

        foreach ($days as $day) {
            if ($day->stable) {
                $streak++;
            } elseif (! $day->inProgress) {
                break;
            }
        }

        return $streak;
    }

    /**
     * Whether the day has a failure that no later run can undo: a failed or
     * expired nightly run, a count that does not match or a late request.
     *
     * @param  Collection<int, stdClass>  $runs
     * @param  Collection<int, stdClass>  $counts
     * @param  Collection<int, stdClass>  $requests
     */
    private function failedForGood(Collection $runs, Collection $counts, Collection $requests): bool
    {
        return $runs->contains(fn (stdClass $run): bool => in_array($run->estado, [RunState::Failed->value, RunState::Expired->value], true))
            || $counts->contains(fn (stdClass $count): bool => ! (bool) $count->cuadra)
            || $requests->contains(fn (stdClass $request): bool => $this->requestProblem($request) !== null);
    }

    /**
     * @param  Collection<int, stdClass>  $runs  The full runs extracted that day.
     * @param  Collection<int, stdClass>  $counts  The nightly counts of the day.
     * @param  Collection<int, stdClass>  $requests  The finished requests that ran from that day.
     */
    private function day(CarbonImmutable $date, Collection $runs, Collection $counts, Collection $requests): StabilityDayData
    {
        $runProblems = [];
        $countProblems = [];
        $requestProblems = [];

        foreach (Company::cases() as $company) {
            foreach (Dataset::cases() as $dataset) {
                $label = "{$company->value} {$dataset->value}";
                $mine = fn (stdClass $row): bool => $row->empresa === $company->value && $row->conjunto === $dataset->value;
                $states = $runs->filter($mine)->pluck('estado');

                if ($states->contains(RunState::Failed->value)) {
                    $runProblems[] = "Falló la corrida nocturna de {$label}.";
                }

                if ($states->contains(RunState::Expired->value)) {
                    $runProblems[] = "Venció la corrida nocturna de {$label}.";
                }

                if (! $states->contains(RunState::Closed->value)) {
                    $runProblems[] = "No hubo corrida nocturna cerrada de {$label}.";
                }

                $rows = $counts->filter($mine);

                if ($rows->isEmpty()) {
                    $countProblems[] = "Falta el conteo de {$label}.";
                }

                foreach ($rows->reject(fn (stdClass $row): bool => (bool) $row->cuadra) as $row) {
                    $countProblems[] = "No cuadra el conteo de {$company->value} {$row->parte}.";
                }
            }
        }

        foreach ($requests as $request) {
            $problem = $this->requestProblem($request);

            if ($problem !== null) {
                $requestProblems[] = $problem;
            }
        }

        return new StabilityDayData(
            date: $date,
            nightlyRunsOk: $runProblems === [],
            countsMatch: $countProblems === [],
            requestsOnTime: $requestProblems === [],
            stable: $runProblems === [] && $countProblems === [] && $requestProblems === [],
            problems: [...$runProblems, ...$countProblems, ...$requestProblems],
        );
    }

    private function requestProblem(stdClass $request): ?string
    {
        if ($request->estado === RequestState::Failed->value) {
            return "La solicitud {$request->id} falló.";
        }

        if ($request->estado === RequestState::Expired->value) {
            return "La solicitud {$request->id} venció.";
        }

        if ($request->terminada_en === null) {
            return "La solicitud {$request->id} terminó sin hora de fin.";
        }

        $timezone = (string) config('app.timezone');
        $seconds = (int) CarbonImmutable::parse((string) $request->correr_desde, $timezone)
            ->diffInSeconds(CarbonImmutable::parse((string) $request->terminada_en, $timezone));

        return $seconds < self::ON_TIME_SECONDS ? null : "La solicitud {$request->id} tardó ".intdiv($seconds, 60).' minutos.';
    }
}
