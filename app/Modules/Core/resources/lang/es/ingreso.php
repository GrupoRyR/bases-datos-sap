<?php

// Sign-in texts, read with __('core::ingreso.<key>').
return [

    'app' => 'Bases SAP',
    'salir' => 'Cerrar sesión',

    'login' => [
        'titulo' => 'Entrar',
        'encabezado' => 'Entra al panel de Bases SAP',
        'detalle' => 'Usa tu cuenta de Microsoft del Grupo RYR.',
        'boton' => 'Entrar con Microsoft',
    ],

    'inicio' => [
        'titulo' => 'Inicio',
        'saludo' => 'Hola, :nombre',
        'rol' => 'Tu rol: :rol',
    ],

    'sin_acceso' => [
        'titulo' => 'Sin acceso',
        'encabezado' => 'Todavía no tienes acceso',
        'detalle' => 'Entraste como :correo, pero aún no tienes un rol en el panel. Pídele a TI que te dé uno.',
    ],

    // Only in local: /dev/entrar.
    'demo' => [
        'titulo' => 'Usuarios de prueba',
        'encabezado' => 'Entra como un usuario de prueba',
        'detalle' => 'Solo en tu equipo y en local: entras sin Microsoft para recorrer el panel.',
        'vacio' => 'Todavía no hay usuarios de prueba. Corre php artisan migrate --seed para crearlos.',
        'boton' => 'Entrar como :nombre',
    ],

    'sesion_cerrada' => 'Cerraste sesión.',
    'error' => 'No pudimos completar el ingreso con Microsoft. Inténtalo de nuevo.',
    // The same for every Application\Auth\RejectionReason: the audit log keeps the reason.
    'rechazado' => 'No puedes entrar con esa cuenta. Si crees que es un error, habla con TI.',
    'cuenta_desactivada' => 'Tu cuenta está desactivada. Si crees que es un error, habla con TI.',

];
