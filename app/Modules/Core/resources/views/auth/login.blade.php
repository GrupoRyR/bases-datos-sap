{{--
    GET /login (core.login): the sign-in page. Shows the flashed status
    (after signing out) or error (a rejected or failed sign-in).
--}}
@extends('core::layouts.base')

@section('title', __('core::ingreso.login.titulo'))

@section('content')
    <h1>{{ __('core::ingreso.login.encabezado') }}</h1>
    <p>{{ __('core::ingreso.login.detalle') }}</p>

    @if (session('status'))
        <p role="status">{{ session('status') }}</p>
    @endif

    @if (session('error'))
        <p role="alert">{{ session('error') }}</p>
    @endif

    <a href="{{ route('core.auth.redirect') }}">{{ __('core::ingreso.login.boton') }}</a>
@endsection
