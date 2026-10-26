<?php

namespace App\Modules\Sap\Console;

use App\Modules\Sap\Application\Requests\SettleRequests;
use App\Modules\Sap\Application\Runs\OpenRuns;
use Illuminate\Console\Command;

/**
 * Expires runs that got no batch for 30 minutes (docs/contrato-robot.md,
 * section 4.1), with their requests, and requests taken 30 minutes ago
 * without finishing (section 7.2). The scheduler runs it every minute.
 */
final class ExpireCommand extends Command
{
    protected $signature = 'sap:vencer';

    protected $description = 'Vence las corridas sin lotes y las solicitudes tomadas que pasaron 30 minutos';

    public function handle(OpenRuns $runs, SettleRequests $requests): int
    {
        $this->info("Corridas vencidas: {$runs->expireIdle()}.");
        $this->info("Solicitudes vencidas: {$requests->expireTaken()}.");

        return self::SUCCESS;
    }
}
