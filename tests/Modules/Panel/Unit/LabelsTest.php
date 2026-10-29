<?php

use App\Modules\Panel\Support\Formats;
use App\Modules\Panel\Support\Labels;
use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\Part;
use Carbon\CarbonImmutable;

it('labels every company, dataset and part in Spanish', function () {
    foreach ([[Company::cases(), 'company'], [Dataset::cases(), 'dataset'], [Part::cases(), 'part']] as [$cases, $method]) {
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
        ->and(Labels::runState('pausada'))->toBe('pausada');
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
