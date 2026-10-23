{{--
    GET /dev/entrar (core.dev.entrar): only in local, from this machine.
    Lists the active users with a role; each one signs in with a POST.
--}}
@extends('core::layouts.base')

@section('title', __('core::ingreso.demo.titulo'))

@section('content')
    <h1>{{ __('core::ingreso.demo.encabezado') }}</h1>
    <p>{{ __('core::ingreso.demo.detalle') }}</p>

    @if ($users->isEmpty())
        <p>{{ __('core::ingreso.demo.vacio') }}</p>
    @else
        <ul>
            @foreach ($users as $user)
                <li>
                    <form method="POST" action="{{ route('core.dev.entrar.usuario', $user) }}">
                        @csrf
                        <p>{{ $user->name }} · {{ $user->email }} · {{ $user->role?->label() }}</p>
                        <button type="submit">{{ __('core::ingreso.demo.boton', ['nombre' => $user->name]) }}</button>
                    </form>
                </li>
            @endforeach
        </ul>
    @endif
@endsection
