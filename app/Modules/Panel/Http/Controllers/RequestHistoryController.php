<?php

namespace App\Modules\Panel\Http\Controllers;

use App\Modules\Panel\Support\Formats;
use App\Modules\Panel\Support\Labels;
use App\Modules\Sap\Contracts\Data\RequesterData;
use App\Modules\Sap\Contracts\Data\RequestHistoryItem;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\RequestState;
use App\Modules\Sap\Contracts\RequestHistory;
use Illuminate\Contracts\View\View;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;

/**
 * GET /panel/solicitudes (panel.solicitudes): the update requests, newest
 * first, with who asked, when, how long they took and how they ended.
 * The optional filters empresa and conjunto are read against the Sap
 * enums; an unknown value is ignored, so a stale link still shows the
 * history. The filter options come from the enums, so a new company or
 * dataset shows with no change here.
 */
final class RequestHistoryController
{
    private const int PER_PAGE = 25;

    public function __invoke(Request $request, RequestHistory $history): View|RedirectResponse
    {
        $company = Company::tryFrom($request->string('empresa')->toString());
        $dataset = Dataset::tryFrom($request->string('conjunto')->toString());
        $page = max(1, $request->integer('page', 1));

        $result = $history->page($page, self::PER_PAGE, $company, $dataset);
        $lastPage = max(1, (int) ceil($result->total / max(1, $result->perPage)));
        $filters = array_filter(['empresa' => $company?->value, 'conjunto' => $dataset?->value]);

        // A page past the end (an old link after a filter change) goes to the last one.
        if ($result->items === [] && $page > $lastPage) {
            return redirect()->route('panel.solicitudes', [...$filters, 'page' => $lastPage]);
        }

        return view('panel::solicitudes', [
            'filters' => [
                'empresa' => $company?->value,
                'conjunto' => $dataset?->value,
                'companies' => array_map(fn (Company $case): array => ['value' => $case->value, 'label' => Labels::company($case->value)], Company::cases()),
                'datasets' => array_map(fn (Dataset $case): array => ['value' => $case->value, 'label' => Labels::dataset($case->value)], Dataset::cases()),
            ],
            'requests' => array_map($this->request(...), $result->items),
            'pages' => [
                'current' => $result->page,
                'last' => $lastPage,
                'older' => $result->page < $lastPage ? route('panel.solicitudes', [...$filters, 'page' => $result->page + 1]) : null,
                'newer' => $result->page > 1 ? route('panel.solicitudes', [...$filters, 'page' => $result->page - 1]) : null,
            ],
        ]);
    }

    /**
     * One request as the view shows it, already in words.
     *
     * @return array<string, mixed>
     */
    private function request(RequestHistoryItem $item): array
    {
        $request = $item->request;
        $state = $request->state->value;

        return [
            'id' => $request->id,
            'company' => Labels::company($request->company->value),
            'dataset' => Labels::dataset($request->dataset->value),
            'scope' => $request->scope === null ? null : Labels::scope($request->scope->value),
            'requestedAt' => ['iso' => Formats::isoDateTime($request->requestedAt), 'text' => Formats::dateTime($request->requestedAt)],
            'duration' => $request->finishedAt === null ? null : Formats::duration($request->requestedAt, $request->finishedAt),
            'state' => Labels::requestState($state),
            'tone' => Labels::requestStateTone($state),
            // Only a queued request says when it runs: at runFrom, or after the
            // sister the robot is serving when runFrom is still unknown.
            'queued' => $request->state === RequestState::Queued,
            'runsAt' => $request->state === RequestState::Queued && $request->runFrom !== null ? Formats::at($request->runFrom) : null,
            // By contract the error carries no secrets; this is TI's panel.
            'error' => in_array($request->state, [RequestState::Failed, RequestState::Expired], true) ? $request->error : null,
            'requesters' => array_map(fn (RequesterData $requester, int $index): array => [
                'origin' => $requester->app ?? __('panel::solicitudes.solicitud.panel'),
                'name' => $requester->name,
                'email' => $requester->email,
                // The first one created the request; the rest joined it later.
                'joinedAt' => $index === 0 ? null : [
                    'iso' => Formats::isoDateTime($requester->joinedAt),
                    'text' => Formats::dateTime($requester->joinedAt),
                ],
            ], $item->requesters, array_keys($item->requesters)),
        ];
    }
}
