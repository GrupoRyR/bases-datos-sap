<?php

namespace Tests\Fixtures\Modules\Demo\Database\Seeders;

use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\Cache;

/**
 * Data every environment needs ("<Module>DatabaseSeeder" convention). It
 * only counts its runs, so the seeder tests need no tables.
 */
final class DemoDatabaseSeeder extends Seeder
{
    public function run(): void
    {
        Cache::increment('demo.seeders.database');
    }
}
