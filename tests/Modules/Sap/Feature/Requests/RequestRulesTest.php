<?php

use App\Modules\Sap\Contracts\Data\UpdateRequestData;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\RequestScope;
use App\Modules\Sap\Contracts\Enums\RequestState;
use App\Modules\Sap\Contracts\UpdateRequests;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;

/*
| How a new update request is placed (docs/contrato-robot.md, section 7.2).
| "The same" request has the same company, dataset and scope; "a sister"
| has the same company and dataset. A request is never refused.
*/

beforeEach(function () {
    Carbon::setTestNow(Carbon::parse('2026-10-26 10:00:00', 'America/Bogota'));
});

function ask(?RequestScope $scope = RequestScope::Customers, Dataset $dataset = Dataset::Maestros, Company $company = Company::Sgx, string $email = 'ana@segurex.com'): UpdateRequestData
{
    return app(UpdateRequests::class)->request($company, $dataset, $scope, $email, 'Ana Ruiz');
}

/** Puts an existing request into a state, with its times. */
function markRequest(int $id, RequestState $state, array $times = []): void
{
    DB::table('update_requests')->where('id', $id)->update(['estado' => $state->value, ...$times]);
}

it('places a first request as pending to run now', function () {
    $request = ask();

    expect($request->created)->toBeTrue()
        ->and($request->state)->toBe(RequestState::Pending)
        ->and($request->runFrom?->format('Y-m-d H:i:s'))->toBe('2026-10-26 10:00:00')
        ->and($request->company)->toBe(Company::Sgx)
        ->and($request->dataset)->toBe(Dataset::Maestros)
        ->and($request->scope)->toBe(RequestScope::Customers);
});

it('joins the same pending or queued request and records who asked', function (RequestState $state) {
    $first = ask();
    markRequest($first->id, $state, ['correr_desde' => now()->addMinute()]);

    $second = ask(email: 'luis@segurex.com');

    expect($second->created)->toBeFalse()
        ->and($second->id)->toBe($first->id)
        ->and(DB::table('update_requests')->count())->toBe(1)
        ->and(DB::table('update_request_requesters')->where('update_request_id', $first->id)->pluck('correo')->all())
        ->toBe(['ana@segurex.com', 'luis@segurex.com']);
})->with([RequestState::Pending, RequestState::Queued]);

it('queues behind a sister that the robot took, until it ends', function (?RequestScope $scope) {
    $taken = ask();
    markRequest($taken->id, RequestState::Taken, ['tomada_en' => now()]);

    $request = ask($scope);

    expect($request->created)->toBeTrue()
        ->and($request->state)->toBe(RequestState::Queued)
        ->and($request->runFrom)->toBeNull();
})->with([
    'the same scope' => [RequestScope::Customers],
    'another scope' => [RequestScope::Items],
    'the whole dataset' => [null],
]);

it('waits 3 minutes after a sister that finished', function () {
    $done = ask();
    markRequest($done->id, RequestState::Done, ['terminada_en' => now()->subMinute()]);

    $request = ask(RequestScope::Prices);

    expect($request->state)->toBe(RequestState::Queued)
        ->and($request->runFrom?->format('H:i:s'))->toBe('10:02:00');
});

it('runs now once 3 minutes passed, or when the sister failed or expired', function (RequestState $state, int $minutesAgo) {
    $previous = ask();
    markRequest($previous->id, $state, ['terminada_en' => now()->subMinutes($minutesAgo)]);

    expect(ask(RequestScope::Prices)->state)->toBe(RequestState::Pending);
})->with([
    'finished 3 minutes ago' => [RequestState::Done, 3],
    'failed a minute ago' => [RequestState::Failed, 1],
    'expired a minute ago' => [RequestState::Expired, 1],
]);

it('keeps sisters of another company or dataset apart', function () {
    $taken = ask();
    markRequest($taken->id, RequestState::Taken, ['tomada_en' => now()]);

    expect(ask(company: Company::Sdc)->state)->toBe(RequestState::Pending)
        ->and(ask(null, Dataset::Cartera)->state)->toBe(RequestState::Pending);
});

it('places a different scope next to a pending sister, for the robot to take together', function () {
    ask();

    expect(ask(RequestScope::Items)->state)->toBe(RequestState::Pending)
        ->and(DB::table('update_requests')->count())->toBe(2);
});

it('moves a request out of a blocked slot and says when it runs', function () {
    Carbon::setTestNow(Carbon::parse('2026-10-26 11:50:00', 'America/Bogota'));

    $request = ask(null, Dataset::Cartera);

    expect($request->state)->toBe(RequestState::Queued)
        ->and($request->runFrom?->format('H:i'))->toBe('12:45');
});

it('moves the 3-minute wait out of a blocked slot too', function () {
    Carbon::setTestNow(Carbon::parse('2026-10-26 11:44:00', 'America/Bogota'));
    $done = ask();
    markRequest($done->id, RequestState::Done, ['terminada_en' => now()]);

    expect(ask()->runFrom?->format('H:i'))->toBe('12:45');
});

it('uses the blocked slots of the configuration', function () {
    config(['sap.requests.blocked_slots' => '10:05']);

    expect(ask()->runFrom?->format('H:i'))->toBe('10:20');
});

it('accepts the scopes of each dataset as the contract lists them', function () {
    expect(RequestScope::forDataset(Dataset::Cartera))->toBe([])
        ->and(RequestScope::forDataset(Dataset::Maestros))->toBe(RequestScope::cases())
        ->and(array_map(fn ($part) => $part->value, RequestScope::Customers->parts()))->toBe(['clientes', 'direcciones', 'contactos'])
        ->and(array_map(fn ($part) => $part->value, RequestScope::Catalogs->parts()))->toBe(['grupos_clientes', 'condiciones_pago', 'municipios']);
});
