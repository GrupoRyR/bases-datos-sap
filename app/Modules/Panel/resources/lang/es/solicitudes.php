<?php

// Texts of the request history (GET /panel/solicitudes), read with
// __('panel::solicitudes.<key>').
return [

    'titulo' => 'Historial de solicitudes',
    'descripcion' => 'Quién pidió datos frescos, cuándo, cuánto tardó y cómo terminó.',

    'filtros' => [
        'titulo' => 'Filtrar solicitudes',
        'empresa' => 'Empresa',
        'conjunto' => 'Conjunto',
        'todas' => 'Todas',
        'todos' => 'Todos',
        'boton' => 'Filtrar',
    ],

    'solicitud' => [
        'titulo' => 'Solicitud :id',
        'todo' => 'Todo el conjunto',
        'pedida' => 'Pedida el :momento',
        'tardo' => 'Tardó :duracion',
        'quien' => 'Quién la pidió',
        'panel' => 'Panel',
        'se_unio' => 'Se unió el :momento',
        'corre' => 'Corre :cuando',
        'espera' => 'Espera a que termine otra',
        'por_que' => 'Por qué falló',
    ],

    'paginas' => [
        'titulo' => 'Páginas del historial',
        'anteriores' => 'Anteriores',
        'recientes' => 'Más recientes',
        'pagina' => 'Página :pagina de :total',
    ],

    'vacio' => 'Aún no hay solicitudes.',

];
