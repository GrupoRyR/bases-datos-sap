<?php

namespace Tests;

use Illuminate\Foundation\Testing\LazilyRefreshDatabase;
use Illuminate\Foundation\Testing\TestCase as BaseTestCase;
use Illuminate\Support\Facades\Http;

abstract class TestCase extends BaseTestCase
{
    // Migrates the test databases only when a test touches them, and wraps
    // each of those tests in a transaction.
    use LazilyRefreshDatabase;

    /**
     * The three databases (docs/plan-bases-sap.md, section 3). Touching any
     * of them migrates the test databases and opens the test transaction on
     * all three.
     *
     * @var list<string>
     */
    protected array $connectionsToTransact = ['app', 'maestros', 'cartera'];

    /**
     * migrate:fresh wipes only the default connection, so the dataset
     * databases are wiped first. Without it, migrating again in the same run
     * (after a test commits, as DDL does on MySQL) would find their tables.
     */
    protected function migrateDatabases(): void
    {
        foreach ($this->connectionsToTransact as $connection) {
            if ($connection !== config('database.default')) {
                $this->artisan('db:wipe', ['--database' => $connection, '--drop-views' => true]);
            }
        }

        $this->artisan('migrate:fresh', $this->migrateFreshUsing());
    }

    protected function setUp(): void
    {
        parent::setUp();

        // Tests never reach real services (SAP, Microsoft, GoDaddy):
        // every outgoing HTTP call must be faked with Http::fake().
        Http::preventStrayRequests();

        // Views render without a compiled public/build.
        $this->withoutVite();
    }
}
