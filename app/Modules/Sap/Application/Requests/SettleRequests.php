<?php

namespace App\Modules\Sap\Application\Requests;

use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\RequestState;
use App\Modules\Sap\Domain\Runs\RunFinished;
use App\Modules\Sap\Domain\Runs\RunState;
use App\Modules\Sap\Models\UpdateRequest;
use Carbon\CarbonImmutable;

/**
 * Ends taken requests (docs/contrato-robot.md, section 7.2) and releases the
 * sisters that were queued behind them: 3 minutes after a request finished
 * well, right away after one failed or expired.
 */
final class SettleRequests
{
    /**
     * A run ended: its taken requests end with it. One that already expired
     * stays expired even if its run closes well (it took too long).
     */
    public function onRunFinished(RunFinished $event): void
    {
        $run = $event->run;
        $state = match ($run->estado) {
            RunState::Closed => RequestState::Done,
            RunState::Failed => RequestState::Failed,
            default => RequestState::Expired,
        };

        $ended = UpdateRequest::query()
            ->whereIn('id', $run->solicitudes)
            ->where('estado', RequestState::Taken)
            ->update([
                'estado' => $state,
                'terminada_en' => now(),
                'error' => $state === RequestState::Done ? null : $run->error,
            ]);

        if ($ended > 0) {
            $this->release($run->empresa, $run->conjunto, $state === RequestState::Done ? CarbonImmutable::now() : null);
        }
    }

    /**
     * Expires requests taken 30 minutes ago that have not finished. Returns how many.
     */
    public function expireTaken(): int
    {
        $expired = 0;

        $stale = UpdateRequest::query()
            ->where('estado', RequestState::Taken)
            ->where('tomada_en', '<=', now()->subMinutes((int) config('sap.requests.taken_expires_minutes')))
            ->get();

        foreach ($stale as $request) {
            $request->forceFill([
                'estado' => RequestState::Expired,
                'terminada_en' => now(),
                'error' => 'Pasaron '.config('sap.requests.taken_expires_minutes').' minutos tomada sin terminar.',
            ])->save();

            $this->release($request->empresa, $request->conjunto, null);
            $expired++;
        }

        return $expired;
    }

    /**
     * Gives a time to the sisters queued without one, once no sister is
     * taken any more.
     */
    private function release(Company $company, Dataset $dataset, ?CarbonImmutable $doneAt): void
    {
        $sisters = fn () => UpdateRequest::query()->sisters($company, $dataset);

        if ($sisters()->where('estado', RequestState::Taken)->exists()) {
            return;
        }

        $runFrom = PlaceRequest::runFrom($doneAt);

        $sisters()->where('estado', RequestState::Queued)->whereNull('correr_desde')->update([
            'estado' => $runFrom->greaterThan(now()) ? RequestState::Queued : RequestState::Pending,
            'correr_desde' => $runFrom,
        ]);
    }
}
