<?php

use Illuminate\Support\Facades\Route;

// Loaded with the "api" middleware, the /api/demo prefix and the "demo.api." name.
Route::get('status', fn () => ['status' => 'ok'])->name('status');
