<?php

use App\Modules\Sap\Domain\Requests\BlockedSlots;
use Carbon\CarbonImmutable;

/*
| Blocked slots (docs/contrato-robot.md, section 7.2, rule 5): while the
| other robots exist they use the VPN at these times, so a request that
| falls 15 minutes or less before or after one waits until the slot ends.
*/

function at(string $time): CarbonImmutable
{
    return CarbonImmutable::parse("2026-10-26 {$time}", 'America/Bogota');
}

it('moves a time inside a slot to the end of the slot, chaining slots that touch', function (string $time, string $runsAt) {
    $slots = BlockedSlots::fromConfig('00:00,05:00,06:00,12:00,12:30', 15);

    expect($slots->next(at($time))->format('Y-m-d H:i'))->toBe($runsAt);
})->with([
    'free morning' => ['10:00', '2026-10-26 10:00'],
    'just before the window' => ['11:44', '2026-10-26 11:44'],
    '15 minutes before is blocked' => ['11:45', '2026-10-26 12:45'],
    // 12:00 and 12:30 windows touch, so 11:50 waits until 12:45.
    'contract example' => ['11:50', '2026-10-26 12:45'],
    'between two touching slots' => ['12:14', '2026-10-26 12:45'],
    'end of the window is free' => ['12:45', '2026-10-26 12:45'],
    'before 05:00' => ['04:50', '2026-10-26 05:15'],
    'gap between 05:00 and 06:00' => ['05:20', '2026-10-26 05:20'],
    'before midnight' => ['23:50', '2026-10-27 00:15'],
    'after midnight' => ['00:10', '2026-10-26 00:15'],
]);

it('reads the slots from configuration and ignores blanks', function () {
    $slots = BlockedSlots::fromConfig(' 08:00 , ,', 10);

    expect($slots->next(at('07:55'))->format('H:i'))->toBe('08:10')
        ->and($slots->next(at('12:00'))->format('H:i'))->toBe('12:00');
});

it('blocks nothing without slots', function () {
    expect(BlockedSlots::fromConfig('', 15)->next(at('12:00'))->format('H:i'))->toBe('12:00');
});
