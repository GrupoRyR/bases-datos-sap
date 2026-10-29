<?php

namespace App\Modules\Panel\Providers;

use App\Support\Modules\ModuleServiceProvider;
use App\Support\Navigation\NavItem;
use App\Support\Navigation\NavRegistry;

/**
 * Panel: the TI panel (docs/plan-bases-sap.md, sections 2 and 6).
 * Owner: the «Panel» session.
 *
 * Web routes: /panel/*, named panel.* (README lists the screens).
 * API routes: /api/panel/*, named panel.api.*.
 * Migrations: 2026_11_03_*. It may use Core and Sap contracts.
 */
final class PanelServiceProvider extends ModuleServiceProvider
{
    /**
     * Every screen of the panel. NavRegistry skips an item until its route
     * exists, so each screen shows up in the menu as soon as its route is
     * added. Screens that change data need core.administrar.
     */
    protected function navigation(NavRegistry $navigation): void
    {
        $navigation->add(
            new NavItem(key: 'panel.estado', label: 'Estado', route: 'panel.estado', permission: 'core.consultar', group: 'Panel', order: 10, mobile: true),
            new NavItem(key: 'panel.solicitudes', label: 'Solicitudes', route: 'panel.solicitudes', permission: 'core.consultar', group: 'Panel', order: 20, activePattern: 'panel.solicitudes*', mobile: true),
            new NavItem(key: 'panel.actualizar', label: 'Actualizar datos', route: 'panel.actualizar', permission: 'core.administrar', group: 'Panel', order: 30, activePattern: 'panel.actualizar*', mobile: true),
            new NavItem(key: 'panel.consulta', label: 'Consulta', route: 'panel.consulta', permission: 'core.consultar', group: 'Panel', order: 40, activePattern: 'panel.consulta*', mobile: true),
            new NavItem(key: 'panel.apps', label: 'Apps conectadas', route: 'panel.apps', permission: 'core.administrar', group: 'Panel', order: 50, activePattern: 'panel.apps*'),
        );
    }
}
