<?php

use Illuminate\Database\QueryException;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Monolog\Formatter\LineFormatter;
use Monolog\Handler\TestHandler;
use Monolog\Level;
use Monolog\Logger;
use Monolog\LogRecord;

/*
| A failed query is logged without its values (audit S-05). Its message
| carries every bound value, and the driver text can quote them too (MySQL's
| "Duplicate entry 'X'"); SAP rows hold NITs, phones and e-mails. The
| tests send the default channel to a Monolog TestHandler and format each
| record as the log file would, stack trace included.
*/

const LOGGED_SECRET = 'NIT-SECRETO-123';

/**
 * Sends the default log channel to a TestHandler and returns it.
 */
function captureDefaultLog(): TestHandler
{
    $handler = new TestHandler;

    Log::extend('capture', function () use ($handler): Logger {
        return new Logger('capture', [$handler]);
    });

    config([
        'logging.channels.capture' => ['driver' => 'capture'],
        'logging.default' => 'capture',
    ]);

    return $handler;
}

/**
 * Every record as the log file would print it, with the stack trace.
 */
function formattedLog(TestHandler $handler): string
{
    $formatter = new LineFormatter(null, null, true, true, true);

    return implode("\n", array_map(
        fn (LogRecord $record): string => $formatter->format($record),
        $handler->getRecords(),
    ));
}

function duplicateUserInsert(): QueryException
{
    $user = [
        'name' => LOGGED_SECRET,
        'email' => strtolower(LOGGED_SECRET).'@example.com',
        'created_at' => now(),
        'updated_at' => now(),
    ];

    DB::table('users')->insert($user);

    try {
        DB::table('users')->insert($user);
    } catch (QueryException $exception) {
        return $exception;
    }

    throw new RuntimeException('The duplicate insert did not fail.');
}

it('logs a failed query once, with its template and connection but without its values', function () {
    $log = captureDefaultLog();
    $exception = duplicateUserInsert();

    report($exception);

    expect($log->getRecords())->toHaveCount(1);

    $record = $log->getRecords()[0];

    expect($record->level)->toBe(Level::Error)
        ->and($record->context)->toMatchArray([
            'connection' => 'app',
            'sql' => $exception->getSql(),
            'exception_class' => $exception::class,
        ])
        ->and($record->context['sql'])->toStartWith('insert into')->toContain('?')
        ->and($record->context['sqlstate'])->toBe('23000')
        ->and(stripos(formattedLog($log), LOGGED_SECRET))->toBeFalse();
});

it('keeps the driver text out of the log, since MySQL quotes the values in it', function () {
    $log = captureDefaultLog();

    $driverText = "Duplicate entry '".LOGGED_SECRET."' for key 'clientes.clientes_nit_unique'";
    $driverError = new PDOException('SQLSTATE[23000]: Integrity constraint violation: 1062 '.$driverText);
    $driverError->errorInfo = ['23000', 1062, $driverText];

    report(new QueryException('maestros', 'insert into `clientes` (`nit`) values (?)', [LOGGED_SECRET], $driverError));

    expect($log->getRecords())->toHaveCount(1)
        ->and($log->getRecords()[0]->context)->toMatchArray([
            'connection' => 'maestros',
            'sqlstate' => '23000',
            'driver_code' => 1062,
            'sql' => 'insert into `clientes` (`nit`) values (?)',
        ])
        ->and(stripos(formattedLog($log), LOGGED_SECRET))->toBeFalse()
        ->and(formattedLog($log))->not->toContain('Duplicate entry');
});

it('still reports any other exception in full', function () {
    $log = captureDefaultLog();

    report(new RuntimeException('Algo falló en la corrida.'));

    expect($log->getRecords())->toHaveCount(1)
        ->and($log->getRecords()[0]->level)->toBe(Level::Error)
        ->and($log->getRecords()[0]->message)->toBe('Algo falló en la corrida.')
        ->and($log->getRecords()[0]->context['exception'])->toBeInstanceOf(RuntimeException::class);
});
