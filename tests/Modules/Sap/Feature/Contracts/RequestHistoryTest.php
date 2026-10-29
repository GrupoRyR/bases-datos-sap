<?php

use App\Modules\Sap\Contracts\ClientAppKeys;
use App\Modules\Sap\Contracts\Data\RequesterData;
use App\Modules\Sap\Contracts\Data\RequestHistoryItem;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\RequestScope;
use App\Modules\Sap\Contracts\Enums\RequestState;
use App\Modules\Sap\Contracts\RequestHistory;
use Illuminate\Support\Facades\DB;

/*
| The update request history, read by the panel through
| Contracts\RequestHistory: newest first, with who asked for each one.
*/

beforeEach(function () {
    $this->travelTo(now()->setDate(2026, 10, 27)->setTime(10, 0));
});

function historyRequest(Company $company = Company::Sgx, Dataset $dataset = Dataset::Maestros): int
{
    return DB::table('update_requests')->insertGetId([
        'empresa' => $company->value, 'conjunto' => $dataset->value, 'estado' => 'pendiente',
        'correr_desde' => now(), 'created_at' => now(), 'updated_at' => now(),
    ]);
}

/** @param  list<RequestHistoryItem>  $items */
function historyIds(array $items): array
{
    return array_map(fn (RequestHistoryItem $item): int => $item->request->id, $items);
}

it('pages the requests newest first and clamps the paging', function () {
    $ids = array_map(fn (int $i): int => historyRequest(), range(1, 30));
    $history = app(RequestHistory::class);

    $second = $history->page(2, 25);

    expect($second->total)->toBe(30)
        ->and($second->page)->toBe(2)
        ->and($second->perPage)->toBe(25)
        ->and(historyIds($second->items))->toBe(array_reverse(array_slice($ids, 0, 5)))
        ->and(historyIds($history->page()->items)[0])->toBe($ids[29])
        ->and($history->page(0, 500)->perPage)->toBe(100)
        ->and($history->page(0, 500)->page)->toBe(1)
        ->and($history->page(-3, 0)->items)->toHaveCount(1)
        ->and($history->page(9)->items)->toBe([]);
});

it('filters by company and dataset', function () {
    historyRequest(Company::Sgx, Dataset::Maestros);
    $sdcCartera = historyRequest(Company::Sdc, Dataset::Cartera);
    $sdcMaestros = historyRequest(Company::Sdc, Dataset::Maestros);
    $history = app(RequestHistory::class);

    expect(historyIds($history->page(company: Company::Sdc)->items))->toBe([$sdcMaestros, $sdcCartera])
        ->and($history->page(company: Company::Sdc, dataset: Dataset::Cartera)->total)->toBe(1)
        ->and(historyIds($history->page(dataset: Dataset::Cartera)->items))->toBe([$sdcCartera]);
});

it('returns the request with who asked, the app by name and the panel as null, in join order', function () {
    $app = app(ClientAppKeys::class)->issue('Gestor de cartera');
    $id = DB::table('update_requests')->insertGetId([
        'empresa' => 'SGX', 'conjunto' => 'MAESTROS', 'parte' => 'clientes', 'estado' => 'terminada',
        'correr_desde' => '2026-10-27 09:00:00', 'tomada_en' => '2026-10-27 09:01:00', 'terminada_en' => '2026-10-27 09:05:00',
        'created_at' => '2026-10-27 08:59:00', 'updated_at' => now(),
    ]);
    DB::table('update_request_requesters')->insert([
        ['update_request_id' => $id, 'client_app_id' => null, 'correo' => 'ana@segurex.com', 'nombre' => 'Ana Ruiz', 'created_at' => '2026-10-27 08:59:00'],
        ['update_request_id' => $id, 'client_app_id' => $app->id, 'correo' => 'luis@segurex.com', 'nombre' => null, 'created_at' => '2026-10-27 08:59:30'],
    ]);
    historyRequest();

    $item = app(RequestHistory::class)->page()->items[1];

    expect($item->request->id)->toBe($id)
        ->and($item->request->scope)->toBe(RequestScope::Customers)
        ->and($item->request->state)->toBe(RequestState::Done)
        ->and($item->request->finishedAt?->format('H:i'))->toBe('09:05')
        ->and(array_map(fn (RequesterData $requester): array => [
            $requester->app, $requester->email, $requester->name, $requester->joinedAt->format('H:i:s'),
        ], $item->requesters))->toBe([
            [null, 'ana@segurex.com', 'Ana Ruiz', '08:59:00'],
            ['Gestor de cartera', 'luis@segurex.com', null, '08:59:30'],
        ]);
});
