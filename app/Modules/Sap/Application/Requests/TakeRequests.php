<?php

namespace App\Modules\Sap\Application\Requests;

use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Contracts\Enums\RequestScope;
use App\Modules\Sap\Contracts\Enums\RequestState;
use App\Modules\Sap\Models\UpdateRequest;
use Illuminate\Support\Facades\DB;

/**
 * The robot takes the requests whose time came (docs/contrato-robot.md,
 * section 7.3), oldest first, in one transaction. Requests of a company and
 * dataset that already has one taken wait: the robot could not open a
 * second run of it.
 */
final class TakeRequests
{
    /**
     * @return list<array{id: int, empresa: string, conjunto: string, parte: string|null, desde: array<string, string|null>|object, solicitada_en: string}>
     */
    public function take(int $max): array
    {
        return DB::transaction(function () use ($max): array {
            $busy = UpdateRequest::query()->where('estado', RequestState::Taken)
                ->get(['empresa', 'conjunto'])
                ->map(fn (UpdateRequest $request): string => $request->empresa->value.':'.$request->conjunto->value)
                ->all();

            $due = UpdateRequest::query()
                ->whereIn('estado', [RequestState::Pending, RequestState::Queued])
                ->whereNotNull('correr_desde')
                ->where('correr_desde', '<=', now())
                ->orderBy('id')
                ->lockForUpdate()
                ->get()
                ->reject(fn (UpdateRequest $request): bool => in_array($request->empresa->value.':'.$request->conjunto->value, $busy, true))
                ->take($max)
                ->values();

            foreach ($due as $request) {
                $request->forceFill(['estado' => RequestState::Taken, 'tomada_en' => now()])->save();
            }

            return $due->map(fn (UpdateRequest $request): array => [
                'id' => $request->id,
                'empresa' => $request->empresa->value,
                'conjunto' => $request->conjunto->value,
                'parte' => $request->parte?->value,
                // An empty JSON object, not a list, when nothing comes in changes.
                'desde' => $this->since($request) ?: (object) [],
                'solicitada_en' => $request->created_at->toIso8601String(),
            ])->all();
        });
    }

    /**
     * For each part that comes in changes, the newest actualizado_en_sap of
     * the company in MySQL; null when there are no rows (bring everything).
     *
     * @return array<string, string|null>
     */
    private function since(UpdateRequest $request): array
    {
        $since = [];

        foreach (RequestScope::partsFor($request->conjunto, $request->parte) as $part) {
            if ($part->tracksSapUpdates()) {
                $since[$part->value] = $this->newest($part, $request->empresa->value);
            }
        }

        return $since;
    }

    private function newest(Part $part, string $company): ?string
    {
        $newest = DB::connection('maestros')->table($part->table())->where('empresa', $company)->max('actualizado_en_sap');

        return $newest === null ? null : now()->parse((string) $newest)->toIso8601String();
    }
}
