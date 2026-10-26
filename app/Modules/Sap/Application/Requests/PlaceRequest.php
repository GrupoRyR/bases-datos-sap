<?php

namespace App\Modules\Sap\Application\Requests;

use App\Modules\Sap\Contracts\Data\UpdateRequestData;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\RequestScope;
use App\Modules\Sap\Contracts\Enums\RequestState;
use App\Modules\Sap\Contracts\UpdateRequests;
use App\Modules\Sap\Domain\Requests\BlockedSlots;
use App\Modules\Sap\Models\UpdateRequest;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use InvalidArgumentException;

/**
 * Places an update request (docs/contrato-robot.md, section 7.2). Requests
 * of one company and dataset are placed one at a time under a lock, so two
 * identical ones arriving together become one.
 *
 * 1. An identical pending or queued request: the new one joins it.
 * 2. A sister taken by the robot: queued, its time set when the sister ends.
 * 3. A sister finished less than 3 minutes ago: queued until 3 minutes after.
 * 4. Otherwise pending, to run now.
 * 5. A time inside a blocked slot moves to the end of the slot, queued.
 */
final class PlaceRequest implements UpdateRequests
{
    public function request(Company $company, Dataset $dataset, ?RequestScope $scope, string $email, ?string $name): UpdateRequestData
    {
        return $this->place($company, $dataset, $scope, $email, $name, null);
    }

    /**
     * @param  int|null  $appId  The app that asked, or null for the panel.
     */
    public function place(Company $company, Dataset $dataset, ?RequestScope $scope, string $email, ?string $name, ?int $appId): UpdateRequestData
    {
        if ($scope !== null && ! in_array($scope, RequestScope::forDataset($dataset), true)) {
            throw new InvalidArgumentException("{$dataset->value} cannot be requested by scope [{$scope->value}].");
        }

        return Cache::lock("sap:solicitudes:{$company->value}:{$dataset->value}", 10)->block(5, fn () => DB::transaction(function () use ($company, $dataset, $scope, $email, $name, $appId) {
            $request = UpdateRequest::query()->sisters($company, $dataset)
                ->where('parte', $scope)
                ->whereIn('estado', [RequestState::Pending, RequestState::Queued])
                ->oldest('id')
                ->first();

            $created = $request === null;
            $request ??= $this->create($company, $dataset, $scope);

            DB::table('update_request_requesters')->insert([
                'update_request_id' => $request->id,
                'client_app_id' => $appId,
                'correo' => mb_strtolower(trim($email)),
                'nombre' => $name === null ? null : trim($name),
                'created_at' => now(),
            ]);

            return $request->toData($created);
        }));
    }

    private function create(Company $company, Dataset $dataset, ?RequestScope $scope): UpdateRequest
    {
        $sisters = fn () => UpdateRequest::query()->sisters($company, $dataset);

        if ($sisters()->where('estado', RequestState::Taken)->exists()) {
            $runFrom = null;
        } else {
            $finishedAt = $sisters()->where('estado', RequestState::Done)->max('terminada_en');
            $runFrom = self::runFrom($finishedAt === null ? null : CarbonImmutable::parse($finishedAt));
        }

        return UpdateRequest::create([
            'empresa' => $company,
            'conjunto' => $dataset,
            'parte' => $scope,
            'estado' => $runFrom === null || $runFrom->greaterThan(now()) ? RequestState::Queued : RequestState::Pending,
            'correr_desde' => $runFrom,
        ]);
    }

    /**
     * When a request may run: 3 minutes after a sister that finished well
     * (now if that already passed), then out of any blocked slot.
     */
    public static function runFrom(?CarbonImmutable $sisterFinishedAt): CarbonImmutable
    {
        $now = CarbonImmutable::now();
        $wait = (int) config('sap.requests.wait_after_done_minutes');
        $at = $sisterFinishedAt === null ? $now : $sisterFinishedAt->addMinutes($wait)->max($now);

        return BlockedSlots::fromConfig(
            (string) config('sap.requests.blocked_slots'),
            (int) config('sap.requests.slot_margin_minutes'),
        )->next($at);
    }
}
