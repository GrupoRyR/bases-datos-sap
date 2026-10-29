<?php

// Labels of the Sap values, read through App\Modules\Panel\Support\Labels.
// Keys are the contract values; a value missing here shows as is.
return [

    'empresas' => [
        'SGX' => 'Segurex',
        'SDC' => 'Derivados',
    ],

    'conjuntos' => [
        'MAESTROS' => 'Maestros',
        'CARTERA' => 'Cartera',
    ],

    'partes' => [
        'clientes' => 'Clientes',
        'proveedores' => 'Proveedores',
        'direcciones' => 'Direcciones',
        'contactos' => 'Contactos',
        'articulos' => 'Artículos',
        'grupos_articulos' => 'Grupos de artículos',
        'marcas' => 'Marcas',
        'precios' => 'Precios',
        'vendedores' => 'Vendedores',
        'grupos_clientes' => 'Grupos de clientes',
        'condiciones_pago' => 'Condiciones de pago',
        'municipios' => 'Municipios',
        'cartera' => 'Cartera',
    ],

    // What a request asks for (RequestScope); the parts it brings go in parentheses.
    'partes_solicitud' => [
        'clientes' => 'Clientes (con direcciones y contactos)',
        'proveedores' => 'Proveedores (con direcciones y contactos)',
        'articulos' => 'Artículos (con grupos y marcas)',
        'precios' => 'Precios',
        'vendedores' => 'Vendedores',
        'catalogos' => 'Catálogos (grupos de clientes, condiciones de pago y municipios)',
    ],

    'estados_solicitud' => [
        'pendiente' => 'Pendiente',
        'en_cola' => 'En cola',
        'tomada' => 'En curso',
        'terminada' => 'Terminada',
        'fallida' => 'Falló',
        'vencida' => 'Venció',
    ],

    'tipos_corrida' => [
        'completa' => 'Nocturna',
        'solicitud' => 'Por solicitud',
    ],

    'estados_corrida' => [
        'abierta' => 'En curso',
        'cerrada' => 'Terminó bien',
        'fallida' => 'Falló',
        'vencida' => 'Venció',
    ],

];
