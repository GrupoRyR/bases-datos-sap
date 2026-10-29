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
