<?php

namespace App\Support\Modules;

use FilesystemIterator;

/**
 * Discovers the modules under a base directory: every immediate
 * subdirectory named in PascalCase is a module. Core comes first because
 * the other modules depend on its contracts; the rest are alphabetical.
 *
 * Plain PHP on purpose, so architecture tests can use it before the
 * application boots.
 */
final class ModuleRegistry
{
    private const MODULE_NAME = '/^[A-Z][A-Za-z0-9]*$/';

    private const CORE = 'Core';

    /** @var list<Module>|null */
    private ?array $modules = null;

    public function __construct(
        private readonly string $path,
        private readonly string $namespace = 'App\\Modules',
    ) {}

    /**
     * @return list<Module>
     */
    public function all(): array
    {
        return $this->modules ??= $this->discover();
    }

    public function find(string $name): ?Module
    {
        foreach ($this->all() as $module) {
            if ($module->name === $name) {
                return $module;
            }
        }

        return null;
    }

    /**
     * @return list<string>
     */
    public function names(): array
    {
        return array_map(fn (Module $module): string => $module->name, $this->all());
    }

    /**
     * @return list<Module>
     */
    private function discover(): array
    {
        $root = realpath($this->path);

        if ($root === false || ! is_dir($root)) {
            return [];
        }

        $names = [];

        foreach (new FilesystemIterator($root, FilesystemIterator::SKIP_DOTS) as $entry) {
            /** @var \SplFileInfo $entry */
            if ($entry->isDir() && preg_match(self::MODULE_NAME, $entry->getFilename()) === 1) {
                $names[] = $entry->getFilename();
            }
        }

        usort($names, function (string $a, string $b): int {
            if ($a === self::CORE || $b === self::CORE) {
                return ($b === self::CORE) <=> ($a === self::CORE);
            }

            return strcmp($a, $b);
        });

        return array_map(fn (string $name): Module => new Module(
            name: $name,
            path: $root.DIRECTORY_SEPARATOR.$name,
            namespace: trim($this->namespace, '\\').'\\'.$name,
        ), $names);
    }
}
