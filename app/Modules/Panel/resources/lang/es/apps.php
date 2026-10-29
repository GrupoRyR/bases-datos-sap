<?php

// Texts of the connected apps (/panel/apps), read with __('panel::apps.<key>').
return [

    'titulo' => 'Apps conectadas',
    'descripcion' => 'Cada app pide actualizaciones con su propia llave. La llave se muestra una sola vez.',

    'nueva' => [
        'titulo' => 'Conectar una app',
        'nombre' => 'Nombre de la app',
        'boton' => 'Crear app y llave',
    ],

    'errores' => [
        'nombre' => 'Escribe el nombre de la app.',
        'nombre_largo' => 'Escribe máximo 100 caracteres.',
        'nombre_usado' => 'Ya hay una app con ese nombre.',
    ],

    'app' => [
        'activa' => 'Activa',
        'revocada' => 'Revocada',
        'revocada_el' => 'Revocada el :momento',
        'llave' => 'Llave :prefijo…',
        'creada' => 'Creada el :momento',
        'ultimo_uso' => 'Último uso el :momento',
        'sin_uso' => 'Nunca la ha usado',
        'rotar' => 'Generar llave nueva',
        'rotar_aviso' => 'La llave actual deja de servir en ese momento.',
        'reactivar' => 'Reactivar con llave nueva',
        'revocar' => 'Revocar',
        'revocar_pregunta' => '¿Revocar la llave de :nombre? La app deja de poder pedir actualizaciones.',
        'revocar_si' => 'Sí, revocar',
    ],

    'vacio' => 'Aún no hay apps conectadas.',

    'llave' => [
        'titulo' => 'Llave de :nombre',
        'campo' => 'Copia la llave ahora',
        'aviso' => 'No se vuelve a mostrar. Si la pierdes, genera una nueva.',
        'volver' => 'Volver a las apps',
    ],

    'revocada' => 'Revocamos la llave de :nombre.',

];
