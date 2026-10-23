<?php

namespace Tests\Fixtures\Modules\Demo\Database\Seeders;

use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\Cache;

/**
 * Local demo data ("<Module>DemoSeeder" convention). It only counts its
 * runs, so the seeder tests need no tables.
 */
final class DemoDemoSeeder extends Seeder
{
    public function run(): void
    {
        Cache::increment('demo.seeders.demo');
    }
}
