<?php

namespace Tests\Modules\Sap\Support;

use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Domain\Columns\ColumnType;
use Illuminate\Testing\TestResponse;
use Tests\TestCase;

/**
 * Sends requests the way the robot does (docs/contrato-robot.md, sections
 * 2 and 3): JSON body, optional gzip, and the four X-Robot-* headers signed
 * with HMAC-SHA256 over the body exactly as it travels.
 */
final class RobotClient
{
    public const KEY = 'r2026a';

    public const SECRET = 'robot-secreto-de-prueba';

    /** Registers the test key as ROBOT_HMAC_KEYS would. */
    public static function configure(): void
    {
        config(['sap.robot.keys' => self::KEY.':'.self::SECRET]);
    }

    /**
     * Opens a run through the API and returns its id. By default a request
     * run of SGX MAESTROS with the customers and their addresses and contacts.
     *
     * @param  array<string, mixed>  $overrides
     */
    public static function openRun(TestCase $test, array $overrides = []): int
    {
        return (int) self::post($test, '/api/robot/v1/corridas', array_merge([
            'conjunto' => 'MAESTROS',
            'empresa' => 'SGX',
            'tipo' => 'solicitud',
            'partes' => ['clientes' => 'cambios', 'direcciones' => 'cambios', 'contactos' => 'cambios'],
            'solicitudes' => [],
            'fecha_corte' => null,
            'extraida_en' => now()->toIso8601String(),
        ], $overrides))->assertCreated()->json('run_id');
    }

    /**
     * A valid row of the part as the robot sends it: invented values for
     * the required columns, null for the rest, then the overrides.
     *
     * @param  array<string, mixed>  $overrides
     * @return array<string, mixed>
     */
    public static function row(Part $part, array $overrides = []): array
    {
        $row = [];

        foreach ($part->columns() as $name => $column) {
            $row[$name] = ! $column->required ? null : match ($column->type) {
                ColumnType::Text => mb_substr('X'.$name, 0, $column->length ?? 255),
                ColumnType::Integer => 1,
                ColumnType::Decimal => '1000.50',
                ColumnType::Boolean => true,
                ColumnType::Date => '2026-10-20',
                ColumnType::DateTime => '2026-10-23T09:15:02-05:00',
            };
        }

        return array_merge($row, $overrides);
    }

    /**
     * The batch body for rows given by column name, in the part's column order.
     *
     * @param  list<array<string, mixed>>  $rows
     * @return array<string, mixed>
     */
    public static function batch(int $number, Part $part, array $rows): array
    {
        $columns = array_keys($part->columns());

        return [
            'batch' => $number,
            'parte' => $part->value,
            'columns' => $columns,
            'rows' => array_map(fn (array $row): array => array_map(fn (string $column): mixed => $row[$column] ?? null, $columns), $rows),
        ];
    }

    public static function sign(string $secret, int $timestamp, string $nonce, string $path, string $body): string
    {
        $canonical = implode("\n", [$timestamp, $nonce, 'POST', $path, hash('sha256', $body)]);

        return 'sha256='.hash_hmac('sha256', $canonical, $secret);
    }

    /**
     * POSTs a signed request. $headers overrides or removes (null) any header
     * after signing, to build broken requests.
     *
     * @param  array<string, mixed>|string  $body
     * @param  array<string, string|null>  $headers
     */
    public static function post(TestCase $test, string $path, array|string $body = [], bool $gzip = false, array $headers = [], ?int $timestamp = null, ?string $nonce = null): TestResponse
    {
        $json = is_string($body) ? $body : (string) json_encode((object) $body, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        $wire = $gzip ? (string) gzencode($json) : $json;
        $timestamp ??= now()->getTimestamp();
        $nonce ??= bin2hex(random_bytes(16));

        $all = array_merge([
            'Content-Type' => 'application/json',
            'Content-Encoding' => $gzip ? 'gzip' : null,
            'X-Robot-Key' => self::KEY,
            'X-Robot-Timestamp' => (string) $timestamp,
            'X-Robot-Nonce' => $nonce,
            'X-Robot-Signature' => self::sign(self::SECRET, $timestamp, $nonce, $path, $wire),
        ], $headers);

        $server = [];

        foreach (array_filter($all, fn (?string $value): bool => $value !== null) as $name => $value) {
            $key = strtoupper(str_replace('-', '_', $name));
            $server[in_array($key, ['CONTENT_TYPE', 'CONTENT_LENGTH'], true) ? $key : 'HTTP_'.$key] = $value;
        }

        return $test->call('POST', $path, [], [], [], $server, $wire);
    }
}
