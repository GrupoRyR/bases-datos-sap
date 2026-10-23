<?php

use Illuminate\Support\Str;
use Pdo\Mysql;

/*
|--------------------------------------------------------------------------
| Connection builder
|--------------------------------------------------------------------------
|
| Every connection shares one driver, chosen by DB_DRIVER: mysql in every
| real environment, sqlite (in memory) in local tests. Host and port are
| shared; each connection names its own database and may have its own user.
|
*/

/** @return array<string, mixed> */
$connection = static function (string $database, ?string $username = null, ?string $password = null): array {
    if (env('DB_DRIVER', 'mysql') === 'sqlite') {
        return [
            'driver' => 'sqlite',
            'database' => $database,
            'prefix' => '',
            'foreign_key_constraints' => env('DB_FOREIGN_KEYS', true),
            'busy_timeout' => null,
            'journal_mode' => null,
            'synchronous' => null,
            'transaction_mode' => 'DEFERRED',
        ];
    }

    return [
        'driver' => 'mysql',
        'host' => env('DB_HOST', '127.0.0.1'),
        'port' => env('DB_PORT', '3306'),
        'database' => $database,
        'username' => $username ?? env('DB_USERNAME', 'root'),
        'password' => $password ?? env('DB_PASSWORD', ''),
        'unix_socket' => env('DB_SOCKET', ''),
        'charset' => 'utf8mb4',
        'collation' => 'utf8mb4_unicode_ci',
        'prefix' => '',
        'prefix_indexes' => true,
        'strict' => true,
        'engine' => null,
        'options' => extension_loaded('pdo_mysql') ? array_filter([
            Mysql::ATTR_SSL_CA => env('MYSQL_ATTR_SSL_CA'),
        ]) : [],
    ];
};

return [

    /*
    |--------------------------------------------------------------------------
    | Default Database Connection Name
    |--------------------------------------------------------------------------
    |
    | Here you may specify which of the database connections below you wish
    | to use as your default connection for database operations. This is
    | the connection which will be utilized unless another connection
    | is explicitly specified when you execute a query / statement.
    |
    */

    'default' => env('DB_CONNECTION', 'app'),

    /*
    |--------------------------------------------------------------------------
    | Database Connections
    |--------------------------------------------------------------------------
    |
    | Three databases (docs/plan-bases-sap.md, section 3): "app" holds the
    | app's own data, "maestros" and "cartera" each hold one SAP dataset.
    | They live on the same server and are built by $connection above.
    |
    */

    'connections' => [

        // The app's own data: requests, runs, panel users, connected apps and audit.
        'app' => $connection(env('DB_DATABASE', 'bases_sap')),

        // One database per dataset, so each consumer app is granted only what it reads.
        'maestros' => $connection(
            env('DB_MAESTROS_DATABASE', 'maestros_sap'),
            env('DB_MAESTROS_USERNAME') ?: null,
            env('DB_MAESTROS_PASSWORD') ?: null,
        ),

        'cartera' => $connection(
            env('DB_CARTERA_DATABASE', 'cartera_sap'),
            env('DB_CARTERA_USERNAME') ?: null,
            env('DB_CARTERA_PASSWORD') ?: null,
        ),

    ],

    /*
    |--------------------------------------------------------------------------
    | Migration Repository Table
    |--------------------------------------------------------------------------
    |
    | This table keeps track of all the migrations that have already run for
    | your application. Using this information, we can determine which of
    | the migrations on disk haven't actually been run on the database.
    |
    */

    'migrations' => [
        'table' => 'migrations',
        'update_date_on_publish' => true,
    ],

    /*
    |--------------------------------------------------------------------------
    | Redis Databases
    |--------------------------------------------------------------------------
    |
    | Redis is an open source, fast, and advanced key-value store that also
    | provides a richer body of commands than a typical key-value system
    | such as Memcached. You may define your connection settings here.
    |
    */

    'redis' => [

        'client' => env('REDIS_CLIENT', 'phpredis'),

        'options' => [
            'cluster' => env('REDIS_CLUSTER', 'redis'),
            'prefix' => env('REDIS_PREFIX', Str::slug((string) env('APP_NAME', 'laravel')).'-database-'),
            'persistent' => env('REDIS_PERSISTENT', false),
        ],

        'default' => [
            'url' => env('REDIS_URL'),
            'host' => env('REDIS_HOST', '127.0.0.1'),
            'username' => env('REDIS_USERNAME'),
            'password' => env('REDIS_PASSWORD'),
            'port' => env('REDIS_PORT', '6379'),
            'database' => env('REDIS_DB', '0'),
            'max_retries' => env('REDIS_MAX_RETRIES', 3),
            'backoff_algorithm' => env('REDIS_BACKOFF_ALGORITHM', 'decorrelated_jitter'),
            'backoff_base' => env('REDIS_BACKOFF_BASE', 100),
            'backoff_cap' => env('REDIS_BACKOFF_CAP', 1000),
        ],

        'cache' => [
            'url' => env('REDIS_URL'),
            'host' => env('REDIS_HOST', '127.0.0.1'),
            'username' => env('REDIS_USERNAME'),
            'password' => env('REDIS_PASSWORD'),
            'port' => env('REDIS_PORT', '6379'),
            'database' => env('REDIS_CACHE_DB', '1'),
            'max_retries' => env('REDIS_MAX_RETRIES', 3),
            'backoff_algorithm' => env('REDIS_BACKOFF_ALGORITHM', 'decorrelated_jitter'),
            'backoff_base' => env('REDIS_BACKOFF_BASE', 100),
            'backoff_cap' => env('REDIS_BACKOFF_CAP', 1000),
        ],

    ],

];
