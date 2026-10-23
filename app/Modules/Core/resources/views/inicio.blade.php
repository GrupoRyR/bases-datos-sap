{{--
    GET / (core.inicio): the home of a user with a role.
--}}
@extends('core::layouts.base')

@section('title', __('core::ingreso.inicio.titulo'))

@section('content')
    <h1>{{ __('core::ingreso.inicio.saludo', ['nombre' => $user->name]) }}</h1>
    <p>{{ __('core::ingreso.inicio.rol', ['rol' => $user->role?->label()]) }}</p>

    <form method="POST" action="{{ route('core.logout') }}">
        @csrf
        <button type="submit">{{ __('core::ingreso.salir') }}</button>
    </form>
@endsection
