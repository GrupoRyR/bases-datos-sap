<?php

use App\Modules\Sap\Domain\Deploy\NightlyWindow;
use App\Modules\Sap\Domain\Requests\BlockedSlots;
use Carbon\CarbonImmutable;

/*
| The nightly window of sap:puede-desplegar reads its times in the app
| timezone, as BlockedSlots does, so both guards move together if
| APP_TIMEZONE ever changes.
*/

it('reads the window in the app timezone, like the blocked slots', function () {
    config()->set('app.timezone', 'UTC');
    $window = NightlyWindow::fromConfig('01:45-02:15');
    $slots = BlockedSlots::fromConfig('02:00', 15);

    $utc = CarbonImmutable::parse('2026-10-27 02:00', 'UTC');
    $bogota = CarbonImmutable::parse('2026-10-27 02:00', 'America/Bogota');

    expect($window->contains($utc))->toBeTrue()
        ->and($slots->contains($utc))->toBeTrue()
        ->and($window->contains($bogota))->toBeFalse()
        ->and($slots->contains($bogota))->toBeFalse();
});

it('refuses a window whose start equals its end', function (string $window) {
    expect(fn () => NightlyWindow::fromConfig($window))->toThrow(InvalidArgumentException::class);
})->with(['02:00-02:00', '0:00-00:00']);

it('still takes a window that crosses midnight', function () {
    expect(NightlyWindow::fromConfig('23:30-00:30')->label())->toBe('23:30-00:30');
});
