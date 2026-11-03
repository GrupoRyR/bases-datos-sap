<?php

use App\Modules\Sap\Models\ClientApp;
use App\Modules\Sap\Models\Run;
use App\Modules\Sap\Models\UpdateRequest;

/*
| The Sap models take by mass assignment only what the code creates them
| with. Key hashes, revocations, results and states set later go through
| forceFill, so a stray input key can never reach them.
*/

it('fills an app with its name only', function () {
    $app = new ClientApp(['nombre' => 'Gestor', 'key_hash' => 'hash', 'key_prefix' => 'bsap_', 'revoked_at' => now(), 'last_used_at' => now()]);

    expect($app->getAttributes())->toBe(['nombre' => 'Gestor']);
});

it('fills a run with what opening it sets', function () {
    $run = new Run([
        'conjunto' => 'MAESTROS', 'empresa' => 'SGX', 'tipo' => 'solicitud', 'partes' => [], 'solicitudes' => [],
        'fecha_corte' => null, 'ventana_desde' => null, 'extraida_en' => '2026-10-26 10:00:00', 'estado' => 'abierta',
        'abierta_lock' => 'MAESTROS:SGX', 'abierta_hasta' => '2026-10-26 10:30:00', 'robot_key' => 'r2026a',
        'batches' => 3, 'filas' => [], 'conteo' => [], 'error' => 'x', 'aplicada_en' => '2026-10-26 10:05:00', 'terminada_en' => '2026-10-26 10:05:00',
    ]);

    expect(array_keys($run->getAttributes()))->toBe([
        'conjunto', 'empresa', 'tipo', 'partes', 'solicitudes', 'fecha_corte', 'ventana_desde',
        'extraida_en', 'estado', 'abierta_lock', 'abierta_hasta', 'robot_key',
    ]);
});

it('fills a request with what placing it sets', function () {
    $request = new UpdateRequest([
        'empresa' => 'SGX', 'conjunto' => 'MAESTROS', 'parte' => 'clientes', 'estado' => 'pendiente', 'correr_desde' => '2026-10-26 10:00:00',
        'tomada_en' => '2026-10-26 10:01:00', 'terminada_en' => '2026-10-26 10:02:00', 'error' => 'x', 'run_id' => 5,
    ]);

    expect(array_keys($request->getAttributes()))->toBe(['empresa', 'conjunto', 'parte', 'estado', 'correr_desde']);
});
