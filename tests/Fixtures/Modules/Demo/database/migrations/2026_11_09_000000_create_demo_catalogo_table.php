<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/*
 * A dataset table: it lives on the "maestros" connection, not on "app".
 * The migrator runs up() and down() with that connection as the default,
 * so Schema::create() needs no connection of its own.
 */
return new class extends Migration
{
    protected $connection = 'maestros';

    public function up(): void
    {
        Schema::create('demo_catalogo', function (Blueprint $table) {
            $table->id();
            $table->string('codigo');
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('demo_catalogo');
    }
};
