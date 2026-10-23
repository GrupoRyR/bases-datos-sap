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
