<?php

use App\Modules\Panel\Support\Formats;
use App\Modules\Panel\Support\Labels;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Contracts\Enums\RequestScope;
use App\Modules\Sap\Contracts\Enums\RequestState;
use Carbon\CarbonImmutable;

it('labels every company, dataset and part in Spanish', function () {
    $groups = [
        [Company::cases(), 'company'],
        [Dataset::cases(), 'dataset'],
        [Part::cases(), 'part'],
        [RequestScope::cases(), 'scope'],
        [RequestState::cases(), 'requestState'],
    ];

    foreach ($groups as [$cases, $method]) {
        foreach ($cases as $case) {
            expect(Labels::{$method}($case->value))->not->toBe($case->value, "{$method} {$case->value} has no label");
        }
    }

    expect(Labels::company('SDC'))->toBe('Derivados')
        ->and(Labels::dataset('MAESTROS'))->toBe('Maestros')
        ->and(Labels::part('grupos_articulos'))->toBe('Grupos de artículos');
});

it('falls back to the raw value of an unknown company, dataset, part or run', function () {
    expect(Labels::company('XYZ'))->toBe('XYZ')
        ->and(Labels::dataset('VENTAS'))->toBe('VENTAS')
        ->and(Labels::part('pedidos'))->toBe('pedidos')
        ->and(Labels::runType('manual'))->toBe('manual')
        ->and(Labels::runState('pausada'))->toBe('pausada')
        ->and(Labels::scope('pedidos'))->toBe('pedidos')
        ->and(Labels::requestState('pausada'))->toBe('pausada')
        ->and(Labels::requestStateTone('pausada'))->toBe('neutral');
});

it('formats numbers and Bogota times the Colombian way', function () {
    $utc = CarbonImmutable::parse('2026-09-29 07:15', 'UTC');

    expect(Formats::number(1234567))->toBe('1.234.567')
        ->and(Formats::number(0))->toBe('0')
        ->and(Formats::dateTime($utc))->toBe('29 sep a las 02:15')
        ->and(Formats::shortDate($utc))->toBe('29 sep')
        ->and(Formats::isoDate($utc))->toBe('2026-09-29')
        ->and(Formats::isoDateTime($utc))->toBe('2026-09-29T02:15:00-05:00');
});

it('says how long something took in whole minutes', function () {
    $from = CarbonImmutable::parse('2026-10-29 10:40', 'America/Bogota');

    expect(Formats::duration($from, $from->addSeconds(59)))->toBe('menos de un minuto')
        ->and(Formats::duration($from, $from->addSeconds(299)))->toBe('4 min')
        ->and(Formats::duration($from, $from->addHour()))->toBe('1 h')
        ->and(Formats::duration($from, $from->addMinutes(125)))->toBe('2 h 5 min')
        ->and(Formats::duration($from, $from->subMinute()))->toBe('menos de un minuto');
});

it('names the day of a time only when it is not today in Bogota', function () {
    $this->travelTo(CarbonImmutable::parse('2026-10-29 23:00', 'America/Bogota'));

    expect(Formats::at(CarbonImmutable::parse('2026-10-29 23:50', 'America/Bogota')))->toBe('a las 23:50')
        ->and(Formats::at(CarbonImmutable::parse('2026-10-30 04:30', 'UTC')))->toBe('a las 23:30')
        ->and(Formats::at(CarbonImmutable::parse('2026-10-30 00:15', 'America/Bogota')))->toBe('el 30 oct a las 00:15');
});
