<?php

// Texts of the lookup (GET and POST /panel/consulta), read with
// __('panel::consulta.<key>').
return [

    'titulo' => 'Consulta',
    'descripcion' => 'Busca un cliente, un proveedor o un artículo para revisar qué llegó de SAP.',

    'parte' => 'Qué buscar',
    'empresa' => 'Empresa',
    'las_dos' => 'Las dos',
    'termino' => 'Código, nombre o NIT',
    'boton' => 'Buscar',

    'errores' => [
        'parte' => 'Elige qué buscar de la lista.',
        'empresa' => 'Elige una empresa de la lista.',
        'termino' => 'Escribe un código, un nombre o un NIT.',
        'termino_corto' => 'Escribe al menos 2 caracteres.',
        'termino_largo' => 'Escribe máximo 100 caracteres.',
    ],

    'resultados' => '{1} :count resultado|[0,*] :count resultados',
    'tope' => 'Se muestran los primeros :max y puede haber más. Afina la búsqueda.',
    'vacio' => 'No encontramos nada con eso.',

    'registro' => [
        'nit' => 'NIT :nit',
        'activo' => 'Activo',
        'inactivo' => 'Inactivo',
        'cambio' => 'Cambió en SAP el :momento',
        'sin_cambio' => 'SAP no da la fecha de cambio',
        'llego' => 'Llegó aquí el :momento',
    ],

];
