{{--
    GET /sin-acceso (core.sin-acceso): a signed-in user without a role.
--}}
@extends('core::layouts.base')

@section('title', __('core::ingreso.sin_acceso.titulo'))

@section('content')
    <h1>{{ __('core::ingreso.sin_acceso.encabezado') }}</h1>
    <p>{{ __('core::ingreso.sin_acceso.detalle', ['correo' => $user?->email]) }}</p>

    <form method="POST" action="{{ route('core.logout') }}">
        @csrf
        <button type="submit">{{ __('core::ingreso.salir') }}</button>
    </form>
@endsection
