<?php

use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Domain\Runs\RunState;
use App\Modules\Sap\Models\Run;
use Illuminate\Support\Facades\DB;
use Tests\Modules\Sap\Support\RobotClient;
use Tests\TestCase;

/*
| Closing a run (docs/contrato-robot.md, section 4.3): MAESTROS upserts by
| key and inactivates what a full part no longer brings; CARTERA replaces
| the company in one transaction and keeps a daily photo. Nothing is ever
| deleted from MAESTROS, and a refused close leaves every table as it was.
*/

beforeEach(function () {
    RobotClient::configure();
    $this->freezeSecond();
});

/**
 * Opens a run, sends one batch per part and returns the run id.
 *
 * @param  array<string, string>  $parts  part => mode
 * @param  array<string, list<array<string, mixed>>>  $rows  part => rows by column name
 * @param  array<string, mixed>  $overrides
 */
function sendRun(TestCase $test, array $parts, array $rows, array $overrides = []): int
{
    $run = RobotClient::openRun($test, ['partes' => $parts, ...$overrides]);
    $number = 0;

    foreach ($rows as $part => $partRows) {
        RobotClient::post($test, "/api/robot/v1/corridas/{$run}/lotes", RobotClient::batch(++$number, Part::from($part), $partRows))
            ->assertCreated();
    }

    return $run;
}

/**
 * @param  array<string, list<array<string, mixed>>>  $rows
 * @param  array<string, mixed>  $extra
 * @return array<string, mixed>
 */
function closeBody(array $rows, array $extra = []): array
{
    return ['batches' => count($rows), 'filas' => array_map('count', $rows), ...$extra];
}

function customer(string $code, array $overrides = []): array
{
    return RobotClient::row(Part::Customers, ['codigo' => $code, 'nombre' => "Cliente {$code}", ...$overrides]);
}

/** @return array<string, mixed> */
function soleCustomer(string $company, string $code): array
{
    return (array) DB::connection('maestros')->table('clientes')->where('empresa', $company)->where('codigo', $code)->sole();
}

it('upserts the customers of the run by company and key', function () {
    DB::connection('maestros')->table('clientes')->insert([
        'empresa' => 'SGX', 'codigo' => 'C1', 'nombre' => 'Nombre viejo', 'activo' => false,
        'actualizado_en_sap' => '2026-10-01 08:00:00', 'sincronizado_en' => '2026-10-01 02:30:00',
    ]);

    $rows = ['clientes' => [customer('C1', ['activo' => true]), customer('C2')]];
    $run = sendRun($this, ['clientes' => 'cambios'], $rows);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", closeBody($rows))
        ->assertOk()
        ->assertExactJson(['run_id' => $run, 'estado' => 'cerrada', 'aplicada_en' => now()->toIso8601String()]);

    $updated = soleCustomer('SGX', 'C1');

    expect($updated['nombre'])->toBe('Cliente C1')
        ->and((bool) $updated['activo'])->toBeTrue()
        ->and($updated['actualizado_en_sap'])->toStartWith('2026-10-23 09:15:02')
        ->and($updated['sincronizado_en'])->toStartWith(now()->format('Y-m-d H:i:s'))
        ->and((int) $updated['corrida_id'])->toBe($run)
        ->and(soleCustomer('SGX', 'C2')['nombre'])->toBe('Cliente C2')
        ->and(Run::find($run)->estado)->toBe(RunState::Closed)
        ->and(DB::table('robot_batches')->count())->toBe(0);
});

it('inactivates what a full part no longer brings, never deletes it, and leaves the other company alone', function () {
    $old = ['nombre' => 'Viejo', 'activo' => true, 'actualizado_en_sap' => '2026-10-01 08:00:00', 'sincronizado_en' => '2026-10-01 02:30:00'];
    DB::connection('maestros')->table('vendedores')->insert([
        ['empresa' => 'SGX', 'codigo' => 1, ...$old],
        ['empresa' => 'SGX', 'codigo' => 2, ...$old],
        ['empresa' => 'SDC', 'codigo' => 2, ...$old],
    ]);

    $rows = ['vendedores' => [RobotClient::row(Part::SalesPeople, ['codigo' => 1, 'nombre' => 'Ana'])]];
    $run = sendRun($this, ['vendedores' => 'todo'], $rows);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", closeBody($rows))->assertOk();

    $active = DB::connection('maestros')->table('vendedores')->orderBy('empresa')->orderBy('codigo')
        ->get()->map(fn (object $row): string => "{$row->empresa}-{$row->codigo}-".((int) $row->activo))->all();

    expect($active)->toBe(['SDC-2-1', 'SGX-1-1', 'SGX-2-0']);
});

it('inactivates nothing for being absent from a part in changes', function () {
    DB::connection('maestros')->table('clientes')->insert([
        'empresa' => 'SGX', 'codigo' => 'C9', 'nombre' => 'Sin cambios', 'activo' => true,
        'actualizado_en_sap' => '2026-10-01 08:00:00', 'sincronizado_en' => '2026-10-01 02:30:00',
    ]);

    $rows = ['clientes' => [customer('C1')]];
    $run = sendRun($this, ['clientes' => 'cambios'], $rows);
    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", closeBody($rows))->assertOk();

    expect((bool) soleCustomer('SGX', 'C9')['activo'])->toBeTrue();
});

it('refreshes all addresses and contacts of each partner sent, even in changes', function () {
    $common = ['activo' => true, 'sincronizado_en' => '2026-10-01 02:30:00'];
    DB::connection('maestros')->table('direcciones')->insert([
        ['empresa' => 'SGX', 'codigo_socio' => 'C1', 'tipo' => 'S', 'nombre' => 'Bodega vieja', ...$common],
        ['empresa' => 'SGX', 'codigo_socio' => 'C7', 'tipo' => 'S', 'nombre' => 'Otro socio', ...$common],
    ]);
    DB::connection('maestros')->table('contactos')->insert([
        ['empresa' => 'SGX', 'contacto_id' => 50, 'codigo_socio' => 'C1', 'nombre' => 'Ya no está', ...$common],
    ]);

    $rows = [
        'clientes' => [customer('C1')],
        'direcciones' => [RobotClient::row(Part::Addresses, ['codigo_socio' => 'C1', 'tipo' => 'B', 'nombre' => 'Principal'])],
        'contactos' => [RobotClient::row(Part::Contacts, ['contacto_id' => 51, 'codigo_socio' => 'C1', 'nombre' => 'Ana'])],
    ];
    $run = sendRun($this, ['clientes' => 'cambios', 'direcciones' => 'cambios', 'contactos' => 'cambios'], $rows);
    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", closeBody($rows))->assertOk();

    $addresses = DB::connection('maestros')->table('direcciones')->orderBy('codigo_socio')->orderBy('nombre')
        ->get()->map(fn (object $row): string => "{$row->codigo_socio}/{$row->nombre}/".((int) $row->activo))->all();
    $contacts = DB::connection('maestros')->table('contactos')->orderBy('contacto_id')
        ->pluck('activo', 'contacto_id')->map(fn (mixed $active): int => (int) $active)->all();

    // Addresses carry no flag of their own: they come in as active.
    expect($addresses)->toBe(['C1/Bodega vieja/0', 'C1/Principal/1', 'C7/Otro socio/1'])
        ->and($contacts)->toBe([50 => 0, 51 => 1]);
});

it('closes a run that brought no changes', function () {
    $run = RobotClient::openRun($this, ['partes' => ['clientes' => 'cambios']]);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 0, 'filas' => ['clientes' => 0]])
        ->assertOk()
        ->assertJsonPath('estado', 'cerrada');
});

it('answers 409 with the missing batches and keeps the run open', function () {
    $rows = ['clientes' => [customer('C1')]];
    $run = sendRun($this, ['clientes' => 'cambios', 'direcciones' => 'cambios'], $rows);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 3, 'filas' => ['clientes' => 1, 'direcciones' => 4]])
        ->assertConflict()
        ->assertJsonPath('faltan', [2, 3]);

    expect(Run::find($run)->isOpen())->toBeTrue()
        ->and(DB::connection('maestros')->table('clientes')->count())->toBe(0);
});

it('answers 409 when the declared rows do not match what arrived', function () {
    $rows = ['clientes' => [customer('C1'), customer('C2')]];
    $run = sendRun($this, ['clientes' => 'cambios'], $rows);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['clientes' => 3]])
        ->assertConflict()
        ->assertJsonPath('faltan', []);

    expect(Run::find($run)->isOpen())->toBeTrue();
});

it('fails the run instead of emptying a full part that came with no rows', function () {
    DB::connection('maestros')->table('marcas')->insert([
        'empresa' => 'SGX', 'codigo' => 1, 'nombre' => 'Acme', 'activo' => true, 'sincronizado_en' => '2026-10-01 02:30:00',
    ]);
    $run = RobotClient::openRun($this, ['partes' => ['marcas' => 'todo']]);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 0, 'filas' => ['marcas' => 0]])
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('filas.marcas');

    expect(Run::find($run)->estado)->toBe(RunState::Failed)
        ->and((bool) DB::connection('maestros')->table('marcas')->value('activo'))->toBeTrue();
});

it('validates the close body against the run', function (array $body, string $field) {
    $run = sendRun($this, ['clientes' => 'cambios'], ['clientes' => [customer('C1')]]);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", $body)
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor($field);

    expect(Run::find($run)->isOpen())->toBeTrue();
})->with([
    'no batches' => [['filas' => ['clientes' => 1]], 'batches'],
    'rows of another part' => [['batches' => 1, 'filas' => ['articulos' => 1]], 'filas'],
    'negative rows' => [['batches' => 1, 'filas' => ['clientes' => -1]], 'filas.clientes'],
    'SAP count outside a full run' => [['batches' => 1, 'filas' => ['clientes' => 1], 'conteo_sap' => ['clientes' => 1]], 'conteo_sap'],
]);

it('requires the SAP count to close a full run', function () {
    $run = RobotClient::openRun($this, ['conjunto' => 'CARTERA', 'tipo' => 'completa', 'partes' => ['cartera' => 'todo'], 'fecha_corte' => '2026-10-25']);
    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", RobotClient::batch(1, Part::Receivables, [RobotClient::row(Part::Receivables)]));

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", ['batches' => 1, 'filas' => ['cartera' => 1]])
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor('conteo_sap');
});

it('replaces the whole CARTERA of the company and leaves the other company alone', function () {
    $line = fn (string $company, string $document): array => [
        ...array_map(fn (mixed $value): mixed => $value, RobotClient::row(Part::Receivables, ['documento' => $document, 'fecha_vencimiento' => '2026-10-20'])),
        'empresa' => $company, 'sincronizado_en' => '2026-10-25 02:30:00',
    ];
    DB::connection('cartera')->table('cartera')->insert([$line('SGX', 'VIEJA-1'), $line('SDC', 'SDC-1')]);

    $rows = ['cartera' => [RobotClient::row(Part::Receivables, ['documento' => 'FV-1']), RobotClient::row(Part::Receivables, ['documento' => 'FV-2'])]];
    $run = sendRun($this, ['cartera' => 'todo'], $rows, ['conjunto' => 'CARTERA', 'fecha_corte' => '2026-10-26']);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", closeBody($rows))->assertOk();

    expect(DB::connection('cartera')->table('cartera')->orderBy('documento')->pluck('documento', 'id')->values()->all())
        ->toBe(['FV-1', 'FV-2', 'SDC-1'])
        ->and(DB::connection('cartera')->table('cartera_fotos')->count())->toBe(0);
});

it('keeps the daily photo of the nightly run, with overdue days counted to the cut-off date', function () {
    $rows = ['cartera' => [RobotClient::row(Part::Receivables, ['documento' => 'FV-1', 'fecha_vencimiento' => '2026-10-20', 'dias' => 6])]];
    $run = sendRun($this, ['cartera' => 'todo'], $rows, ['conjunto' => 'CARTERA', 'tipo' => 'completa', 'fecha_corte' => '2026-10-25']);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", closeBody($rows, ['conteo_sap' => ['cartera' => 1]]))->assertOk();

    $photo = DB::connection('cartera')->table('cartera_fotos')->sole();

    expect($photo->fecha_corte)->toStartWith('2026-10-25')
        // The query counted days to the run (6); the photo stands for the cut-off day.
        ->and((int) $photo->dias)->toBe(5)
        ->and((int) DB::connection('cartera')->table('cartera')->value('dias'))->toBe(6);
});

it('replaces a photo of the same company and day', function () {
    foreach (['FV-1', 'FV-2'] as $document) {
        $rows = ['cartera' => [RobotClient::row(Part::Receivables, ['documento' => $document])]];
        $run = sendRun($this, ['cartera' => 'todo'], $rows, ['conjunto' => 'CARTERA', 'tipo' => 'completa', 'fecha_corte' => '2026-10-25']);
        RobotClient::post($this, "/api/robot/v1/corridas/{$run}/cerrar", closeBody($rows, ['conteo_sap' => ['cartera' => 1]]))->assertOk();
    }

    expect(DB::connection('cartera')->table('cartera_fotos')->pluck('documento')->all())->toBe(['FV-2']);
});
