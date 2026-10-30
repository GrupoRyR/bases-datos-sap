<?php

// Texts of the «Actualizar datos» form (GET and POST /panel/actualizar),
// read with __('panel::actualizar.<key>').
return [

    'titulo' => 'Actualizar datos',
    'descripcion' => 'Pide a SAP datos frescos de una empresa.',
    'regla' => 'Si ya hay una igual esperando, te unes a ella; si se actualizó hace menos de 3 minutos o cae en una franja de los otros robots, queda en cola. Nunca se rechaza.',
    'historial' => 'Ver el historial de solicitudes',

    'empresa' => 'Empresa',
    'datos' => 'Qué actualizar',
    'opcion' => ':conjunto: :parte',
    'todo' => 'todo',
    'boton' => 'Actualizar datos',

    'errores' => [
        'empresa' => 'Elige una de las empresas de la lista.',
        'datos' => 'Elige qué actualizar de la lista.',
    ],

    // The flash message after asking, from the request the contract returns.
    'resultado' => [
        'unida' => 'Ya había una solicitud igual esperando; te uniste a la solicitud :id.',
        'unida_hora' => 'Ya había una solicitud igual esperando; te uniste a la solicitud :id, que se actualizará :cuando.',
        'pendiente' => 'Pedimos los datos a SAP (solicitud :id). Suele tardar unos minutos.',
        'en_cola_hora' => 'Se actualizará :cuando (solicitud :id).',
        'en_cola' => 'Hay otra actualización en curso; esta sigue después (solicitud :id).',
    ],

];
