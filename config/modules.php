<?php

/*
|--------------------------------------------------------------------------
| Modules
|--------------------------------------------------------------------------
|
| Reserved date prefix for each module's migrations (docs/arquitectura.md).
| Every module loads its own migrations, so the prefix keeps their order
| stable and their file names free of collisions.
| tests/Architecture/ModulesTest.php fails on a migration without it.
|
*/

return [

    'migration_prefixes' => [
        'Core' => '2026_11_01',
        'Sap' => '2026_11_02',
        'Panel' => '2026_11_03',
    ],

];
