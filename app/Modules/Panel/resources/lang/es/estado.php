<?php

// Texts of the status screen (GET /panel), read with __('panel::estado.<key>').
return [

    'titulo' => 'Estado de los datos',
    'descripcion' => 'Lo que trajo el robot de SAP por empresa y conjunto.',

    'estabilidad' => [
        'titulo' => 'Días estables',
        'contador' => 'Estable: :dias de :meta días',
        'detalle' => 'Un día es estable si las corridas nocturnas terminaron bien, los conteos cuadraron y cada solicitud terminó en menos de 10 minutos.',
        'franja' => 'Últimos :dias días, del más reciente al más antiguo',
        'estable' => 'Estable',
        'con_fallas' => 'Con fallas',
        'en_curso' => 'En curso',
        'problemas' => 'Qué falló en los días con fallas',
        'a_mano' => 'Nadie corrigió datos a mano: lo revisa TI.',
    ],

    'conjunto' => [
        'actualizado' => 'Actualizado el :momento',
        'sin_datos' => 'Sin datos aún',
        'filas' => 'Filas por tabla',
    ],

    'corrida' => [
        'titulo' => 'Última corrida',
        'empezo' => 'Empezó el :momento',
        'termino' => 'Terminó el :momento',
        'por_que' => 'Por qué falló',
        'ninguna' => 'Aún no hay corridas.',
    ],

    'vacio' => [
        'titulo' => 'Aún no hay conjuntos',
        'detalle' => 'Cuando el robot traiga datos de SAP, aquí verás cada empresa.',
    ],

];
