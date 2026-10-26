<?php

namespace App\Modules\Sap\Console;

use App\Modules\Sap\Contracts\ClientAppKeys;
use Illuminate\Console\Command;
use InvalidArgumentException;

/**
 * Creates the key of an app until the panel does it. The key is printed
 * once and cannot be recovered: copy it to the app's .env.
 */
final class CreateAppKeyCommand extends Command
{
    protected $signature = 'sap:app {nombre : Nombre de la app, p. ej. "Gestor de cartera"}';

    protected $description = 'Crea la llave con la que una app pide actualizaciones';

    public function handle(ClientAppKeys $keys): int
    {
        try {
            $issued = $keys->issue((string) $this->argument('nombre'));
        } catch (InvalidArgumentException $invalid) {
            $this->error($invalid->getMessage());

            return self::FAILURE;
        }

        $this->info("Llave de «{$issued->name}» (id {$issued->id}). Cópiala ahora: no se vuelve a mostrar.");
        $this->line($issued->key);

        return self::SUCCESS;
    }
}
