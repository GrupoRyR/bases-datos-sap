<?php

use Illuminate\Support\Facades\Route;

// Loaded with the "web" middleware, the /demo prefix and the "demo." name.
Route::get('ping', fn () => 'pong')->name('ping');
