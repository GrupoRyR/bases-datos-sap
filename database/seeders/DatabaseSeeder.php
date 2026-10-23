<?php

namespace Database\Seeders;

use App\Support\Modules\ModuleRegistry;
use Illuminate\Database\Console\Seeds\WithoutModelEvents;
use Illuminate\Database\Seeder;

class DatabaseSeeder extends Seeder
{
    use WithoutModelEvents;

    /**
     * Seed the application's database from the modules: every
     * <Module>DatabaseSeeder, then, only in local, every <Module>DemoSeeder.
     */
    public function run(ModuleRegistry $modules): void
    {
        $this->callModuleSeeders($modules, 'DatabaseSeeder');

        if (app()->environment('local')) {
            $this->callModuleSeeders($modules, 'DemoSeeder');
        }
    }

    private function callModuleSeeders(ModuleRegistry $modules, string $suffix): void
    {
        foreach ($modules->all() as $module) {
            if (class_exists($seeder = $module->seederClass($suffix))) {
                $this->call($seeder);
            }
        }
    }
}
