<?php

use Illuminate\Support\Facades\Route;

/*
| The private local disk (storage/app/private) is never served over HTTP
| (audit S-12): with "serve" on, Laravel registers GET /storage/{path} and
| answers any file of the disk to a valid signed URL.
*/

it('registers no route that serves the local disk', function () {
    expect(config('filesystems.disks.local.serve'))->toBeFalse()
        ->and(Route::has('storage.local'))->toBeFalse()
        ->and(Route::has('storage.local.upload'))->toBeFalse();
});

it('answers 404 to a request for a file of the local disk', function () {
    $this->get('/storage/robot.log')->assertNotFound();
});
