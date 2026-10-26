<?php

namespace App\Modules\Sap\Console;

use App\Modules\Sap\Application\Runs\OpenRuns;
use Illuminate\Console\Command;

/**
 * Expires runs that got no batch for 30 minutes (docs/contrato-robot.md,
 * section 4.1). The scheduler runs it every minute.
 */
final class ExpireCommand extends Command
{
    protected $signature = 'sap:vencer';

    protected $description = 'Vence las corridas abiertas que pasaron 30 minutos sin recibir lotes';

    public function handle(OpenRuns $runs): int
    {
        $this->info("Corridas vencidas: {$runs->expireIdle()}.");

        return self::SUCCESS;
    }
}
