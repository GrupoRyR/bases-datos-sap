<?php

namespace App\Support\Modules;

/**
 * One module under app/Modules (docs/arquitectura.md).
 *
 * The lowercase key names everything the module exposes: route names
 * ("sap.*"), the view and translation namespace ("sap::") and the
 * config key ("sap").
 */
final readonly class Module
{
    /**
     * @param  string  $name  Directory name, e.g. "Sap".
     * @param  string  $path  Absolute path of the module root.
     * @param  string  $namespace  Root namespace, e.g. "App\Modules\Sap".
     */
    public function __construct(
        public string $name,
        public string $path,
        public string $namespace,
    ) {}

    public function key(): string
    {
        return strtolower($this->name);
    }

    /**
     * Absolute path of a file or directory inside the module.
     */
    public function path(string $relative = ''): string
    {
        $relative = trim(str_replace(['/', '\\'], DIRECTORY_SEPARATOR, $relative), DIRECTORY_SEPARATOR);

        return $relative === '' ? $this->path : $this->path.DIRECTORY_SEPARATOR.$relative;
    }

    /**
     * The service provider every module must have.
     */
    public function providerClass(): string
    {
        return "{$this->namespace}\\Providers\\{$this->name}ServiceProvider";
    }

    /**
     * A conventional seeder, e.g. "DatabaseSeeder" gives SapDatabaseSeeder.
     */
    public function seederClass(string $suffix): string
    {
        return "{$this->namespace}\\Database\\Seeders\\{$this->name}{$suffix}";
    }
}
