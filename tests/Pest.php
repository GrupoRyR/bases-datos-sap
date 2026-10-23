<?php

use Tests\TestCase;

/*
|--------------------------------------------------------------------------
| Test case
|--------------------------------------------------------------------------
|
| Every test runs on Tests\TestCase: lazily refreshed test databases,
| no Vite and no stray HTTP requests.
|
*/

pest()->extend(TestCase::class)->in('Feature', 'Unit');
