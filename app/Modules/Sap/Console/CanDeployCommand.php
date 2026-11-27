<?php

namespace App\Modules\Sap\Console;

use App\Modules\Sap\Contracts\Enums\RequestState;
use App\Modules\Sap\Domain\Deploy\NightlyWindow;
use App\Modules\Sap\Domain\Requests\BlockedSlots;
use App\Modules\Sap\Domain\Runs\RunState;
use App\Modules\Sap\Models\Run;
use App\Modules\Sap\Models\UpdateRequest;
use Carbon\CarbonImmutable;
use Illuminate\Console\Command;
use InvalidArgumentException;

/**
 * Tells the deploy dispatcher whether a deploy may start now. Maintenance
 * mode in the middle of a run kills it: the robot retries a 5xx only 3 times
 * within 14 seconds (robot/etl/api.py). Prints `ok` and exits 0, or prints
 * the first reason that applies and exits 1. It only reads: it never
 * expires a stale run or request (that is sap:vencer's job).
 */
final class CanDeployCommand extends Command
{
    protected $signature = 'sap:puede-desplegar';

    protected $description = 'Dice si se puede desplegar ahora: fuera de las franjas, de la ventana nocturna y sin corridas ni solicitudes en curso';

    public function handle(): int
    {
        // In the app timezone, as the database stores it; each window converts it to its own.
        $reason = $this->reason(CarbonImmutable::now());

        $this->line($reason ?? 'ok');

        return $reason === null ? self::SUCCESS : self::FAILURE;
    }

    private function reason(CarbonImmutable $now): ?string
    {
        $margin = (int) config('sap.requests.slot_margin_minutes');

        if (BlockedSlots::fromConfig((string) config('sap.requests.blocked_slots'), $margin)->contains($now)) {
            return "Ahora no: estás a {$margin} minutos o menos de una franja bloqueada.";
        }

        $configured = (string) config('sap.deploy.nightly_window');

        try {
            $window = NightlyWindow::fromConfig($configured);
        } catch (InvalidArgumentException) {
            return "Ahora no: la ventana nocturna configurada no es válida ({$configured}).";
        }

        if ($window->contains($now)) {
            return "Ahora no: estás en la ventana de la corrida nocturna ({$window->label()}).";
        }

        // Same test as Run::isOpen(): an open run past its idle window no longer takes batches.
        if (Run::query()->where('estado', RunState::Open)->where('abierta_hasta', '>', $now)->exists()) {
            return 'Ahora no: hay una corrida del robot abierta.';
        }

        // The complement of SettleRequests::expireTaken().
        $expiresBefore = $now->subMinutes((int) config('sap.requests.taken_expires_minutes'));

        if (UpdateRequest::query()->where('estado', RequestState::Taken)
            ->where(fn ($query) => $query->whereNull('tomada_en')->orWhere('tomada_en', '>', $expiresBefore))
            ->exists()) {
            return 'Ahora no: hay una solicitud tomada por el robot que no ha vencido.';
        }

        return null;
    }
}
