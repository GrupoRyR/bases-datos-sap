<?php

namespace App\Modules\Sap\Application\Panel;

use App\Modules\Sap\Contracts\Data\RequesterData;
use App\Modules\Sap\Contracts\Data\RequestHistoryItem;
use App\Modules\Sap\Contracts\Data\RequestHistoryPage;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\RequestHistory;
use App\Modules\Sap\Models\UpdateRequest;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;
use stdClass;

/**
 * Pages update_requests newest first and loads the requesters of the whole
 * page in one query, with the name of the app that asked.
 */
final class DatabaseRequestHistory implements RequestHistory
{
    private const MAX_PER_PAGE = 100;

    public function page(int $page = 1, int $perPage = 25, ?Company $company = null, ?Dataset $dataset = null): RequestHistoryPage
    {
        $page = max(1, $page);
        $perPage = min(max(1, $perPage), self::MAX_PER_PAGE);

        $query = UpdateRequest::query()
            ->when($company, fn ($query, Company $company) => $query->where('empresa', $company->value))
            ->when($dataset, fn ($query, Dataset $dataset) => $query->where('conjunto', $dataset->value));

        $total = (clone $query)->count();
        $requests = $query->orderByDesc('id')->forPage($page, $perPage)->get();

        $requesters = DB::table('update_request_requesters AS requester')
            ->leftJoin('client_apps AS app', 'app.id', '=', 'requester.client_app_id')
            ->whereIn('requester.update_request_id', $requests->modelKeys())
            ->orderBy('requester.created_at')
            ->orderBy('requester.id')
            ->get(['requester.update_request_id', 'app.nombre AS app', 'requester.correo', 'requester.nombre', 'requester.created_at'])
            ->groupBy('update_request_id');

        $timezone = (string) config('app.timezone');

        return new RequestHistoryPage(
            items: $requests->map(fn (UpdateRequest $request): RequestHistoryItem => new RequestHistoryItem(
                request: $request->toData(),
                requesters: $requesters->get($request->id, collect())
                    ->map(fn (stdClass $requester): RequesterData => new RequesterData(
                        app: $requester->app,
                        email: $requester->correo,
                        name: $requester->nombre,
                        joinedAt: CarbonImmutable::parse((string) $requester->created_at, $timezone),
                    ))
                    ->values()
                    ->all(),
            ))->values()->all(),
            total: $total,
            page: $page,
            perPage: $perPage,
        );
    }
}
