<?php

use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Models\Run;
use Illuminate\Support\Facades\DB;
use Tests\Modules\Sap\Support\RobotClient;

/*
| Receiving batches (docs/contrato-robot.md, section 4.2). Batches are kept
| until the run closes; nothing reaches the MAESTROS tables here.
*/

beforeEach(function () {
    RobotClient::configure();
    $this->freezeSecond();
    $this->run = RobotClient::openRun($this);
    $this->path = "/api/robot/v1/corridas/{$this->run}/lotes";
});

/** @return list<array<string, mixed>> */
function customers(string ...$codes): array
{
    return array_map(fn (string $code): array => RobotClient::row(Part::Customers, ['codigo' => $code]), $codes);
}

it('accepts a batch and keeps it for the close, without touching MAESTROS', function () {
    RobotClient::post($this, $this->path, RobotClient::batch(1, Part::Customers, customers('C1', 'C2')))
        ->assertCreated()
        ->assertExactJson(['batch' => 1, 'rows' => 2]);

    $batch = DB::table('robot_batches')->sole();

    expect($batch->parte)->toBe('clientes')
        ->and($batch->rows_count)->toBe(2)
        ->and(json_decode($batch->rows, true)[1][0])->toBe('C2')
        ->and(DB::connection('maestros')->table('clientes')->count())->toBe(0);
});

it('accepts gzip batches and numbers batches across parts of the run', function () {
    RobotClient::post($this, $this->path, RobotClient::batch(1, Part::Customers, customers('C1')), gzip: true)->assertCreated();
    RobotClient::post($this, $this->path, RobotClient::batch(2, Part::Addresses, [RobotClient::row(Part::Addresses, ['codigo_socio' => 'C1'])]))->assertCreated();

    expect(DB::table('robot_batches')->pluck('parte', 'batch')->all())->toBe([1 => 'clientes', 2 => 'direcciones']);
});

it('answers 200 with duplicate to the same batch sent again, compressed or not', function () {
    $body = RobotClient::batch(1, Part::Customers, customers('C1', 'C2'));

    RobotClient::post($this, $this->path, $body)->assertCreated();
    RobotClient::post($this, $this->path, $body, gzip: true)
        ->assertOk()
        ->assertExactJson(['batch' => 1, 'rows' => 2, 'duplicate' => true]);

    expect(DB::table('robot_batches')->count())->toBe(1);
});

it('answers 409 to the same batch number with another body', function () {
    RobotClient::post($this, $this->path, RobotClient::batch(1, Part::Customers, customers('C1')))->assertCreated();

    RobotClient::post($this, $this->path, RobotClient::batch(1, Part::Customers, customers('C9')))
        ->assertConflict()
        ->assertJsonPath('estado', 'abierta');
});

it('refuses a key repeated in the batch or in an earlier batch of the run', function () {
    RobotClient::post($this, $this->path, RobotClient::batch(1, Part::Customers, customers('C1', 'C2', 'C1')))
        ->assertUnprocessable()
        ->assertJsonValidationErrors(['rows.2.codigo' => 'La llave se repite en la corrida.']);

    RobotClient::post($this, $this->path, RobotClient::batch(1, Part::Customers, customers('C1')))->assertCreated();

    RobotClient::post($this, $this->path, RobotClient::batch(2, Part::Customers, customers('C3', 'C1')))
        ->assertUnprocessable()
        ->assertJsonValidationErrors(['rows.1.codigo']);

    expect(Run::find($this->run)->lotes_rechazados)->toBe(2);
});

it('lets the same key appear in another part', function () {
    $this->run = RobotClient::openRun($this, ['empresa' => 'SDC', 'partes' => ['clientes' => 'cambios', 'proveedores' => 'cambios']]);
    $path = "/api/robot/v1/corridas/{$this->run}/lotes";

    RobotClient::post($this, $path, RobotClient::batch(1, Part::Customers, customers('C1')))->assertCreated();
    RobotClient::post($this, $path, RobotClient::batch(2, Part::Suppliers, [RobotClient::row(Part::Suppliers, ['codigo' => 'C1'])]))->assertCreated();
});

it('never checks repeated lines in CARTERA, which has no key', function () {
    $run = RobotClient::openRun($this, ['conjunto' => 'CARTERA', 'partes' => ['cartera' => 'todo'], 'fecha_corte' => '2026-10-26']);
    $line = RobotClient::row(Part::Receivables, ['documento' => 'FV-1']);

    RobotClient::post($this, "/api/robot/v1/corridas/{$run}/lotes", RobotClient::batch(1, Part::Receivables, [$line, $line]))
        ->assertCreated();
});

it('refuses with 422 what does not fit the run or the contract, and the run stays open', function (Closure $body, string $field) {
    RobotClient::post($this, $this->path, $body())
        ->assertUnprocessable()
        ->assertJsonValidationErrorFor($field);

    expect(Run::find($this->run)->isOpen())->toBeTrue()
        ->and(DB::table('robot_batches')->count())->toBe(0);
})->with([
    'part not in the run' => [fn () => RobotClient::batch(1, Part::Items, [RobotClient::row(Part::Items)]), 'parte'],
    'unknown part' => [fn () => ['batch' => 1, 'parte' => 'auditoria', 'columns' => ['x'], 'rows' => [[1]]], 'parte'],
    'batch zero' => [fn () => RobotClient::batch(0, Part::Customers, customers('C1')), 'batch'],
    'batch as text' => [fn () => ['batch' => '1'] + RobotClient::batch(1, Part::Customers, customers('C1')), 'batch'],
    'no rows' => [fn () => RobotClient::batch(1, Part::Customers, []), 'rows'],
    'over 1,000 rows' => [fn () => RobotClient::batch(1, Part::Customers, customers(...array_map(fn (int $i): string => "C{$i}", range(1, 1001)))), 'rows'],
    'bad value' => [fn () => RobotClient::batch(1, Part::Customers, [RobotClient::row(Part::Customers, ['activo' => 'Y'])]), 'rows.0.activo'],
    'missing column' => [fn () => ['columns' => ['codigo']] + RobotClient::batch(1, Part::Customers, customers('C1')), 'columns'],
]);

it('keeps the run alive for 30 minutes after each accepted batch', function () {
    $this->travel(25)->minutes();
    RobotClient::post($this, $this->path, RobotClient::batch(1, Part::Customers, customers('C1')))->assertCreated();

    $this->travel(25)->minutes();
    RobotClient::post($this, $this->path, RobotClient::batch(2, Part::Customers, customers('C2')))->assertCreated();

    expect(Run::find($this->run)->abierta_hasta->equalTo(now()->addMinutes(30)))->toBeTrue();
});

it('answers 409 with the state once the run is no longer open, and 404 to an unknown run', function () {
    RobotClient::post($this, "/api/robot/v1/corridas/{$this->run}/fallar", ['error' => 'Falla de VPN']);

    RobotClient::post($this, $this->path, RobotClient::batch(1, Part::Customers, customers('C1')))
        ->assertConflict()
        ->assertJsonPath('estado', 'fallida');

    RobotClient::post($this, '/api/robot/v1/corridas/999/lotes', RobotClient::batch(1, Part::Customers, customers('C1')))
        ->assertNotFound();
});
