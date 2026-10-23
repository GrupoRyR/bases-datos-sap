<?php

use Tests\TestCase;

/*
|--------------------------------------------------------------------------
| Test case
|--------------------------------------------------------------------------
|
| Every test runs on Tests\TestCase: lazily refreshed test databases,
| no Vite and no stray HTTP requests. Module tests live in
| tests/Modules/<Modulo>/{Unit,Feature}.
|
*/

pest()->extend(TestCase::class)->in('Architecture', 'Feature', 'Modules', 'Unit');
