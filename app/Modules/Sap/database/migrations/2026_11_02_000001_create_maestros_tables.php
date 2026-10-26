<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * The MAESTROS tables in maestros_sap (docs/plan-bases-sap.md, section 4;
 * columns from docs/contrato-robot.md, section 5.2). Every row carries the
 * company, its SAP key, activo, actualizado_en_sap and sincronizado_en, and
 * is unique by company and key. Rows are never deleted: what stops coming
 * from SAP is marked inactive.
 *
 * Apps never read these tables, only the v_* views of the next migration.
 */
return new class extends Migration
{
    protected $connection = 'maestros';

    public function up(): void
    {
        $this->master('clientes', ['codigo'], fn (Blueprint $table) => $this->businessPartner($table));
        $this->master('proveedores', ['codigo'], fn (Blueprint $table) => $this->businessPartner($table));

        $this->master('direcciones', ['codigo_socio', 'tipo', 'nombre'], function (Blueprint $table) {
            $table->string('codigo_socio', 50);
            $table->string('tipo', 1);
            $table->string('nombre', 50);
            $table->string('calle')->nullable();
            $table->string('barrio')->nullable();
            $table->string('ciudad')->nullable();
            $table->string('municipio_codigo', 50)->nullable();
            $table->string('departamento')->nullable();
            $table->string('pais', 50)->nullable();
            $table->string('codigo_postal', 50)->nullable();
        });

        $this->master('contactos', ['contacto_id'], function (Blueprint $table) {
            $table->integer('contacto_id');
            $table->string('codigo_socio', 50);
            $table->string('nombre');
            $table->string('nombres')->nullable();
            $table->string('apellidos')->nullable();
            $table->string('cargo')->nullable();
            $table->string('telefono', 50)->nullable();
            $table->string('celular', 50)->nullable();
            $table->string('correo')->nullable();
        });

        $this->master('articulos', ['codigo'], function (Blueprint $table) {
            $table->string('codigo', 50);
            $table->string('nombre');
            $table->string('nombre_extranjero')->nullable();
            $table->integer('grupo_codigo')->nullable();
            $table->integer('marca_codigo')->nullable();
            $table->string('unidad_venta', 50)->nullable();
            $table->string('codigo_barras')->nullable();
            $table->boolean('inventariable')->nullable();
            $table->boolean('de_venta')->nullable();
            $table->boolean('de_compra')->nullable();
            $table->date('creado_en_sap')->nullable();
        });

        $this->master('grupos_articulos', ['codigo'], fn (Blueprint $table) => $this->catalog($table));
        $this->master('marcas', ['codigo'], fn (Blueprint $table) => $this->catalog($table));

        // Only the PÚBLICA price list, one price per item.
        $this->master('precios', ['articulo_codigo'], function (Blueprint $table) {
            $table->string('articulo_codigo', 50);
            $table->integer('lista_codigo');
            $table->string('lista_nombre');
            $table->decimal('precio', 19, 2)->nullable();
            $table->string('moneda', 10)->nullable();
        });

        $this->master('vendedores', ['codigo'], function (Blueprint $table) {
            $table->integer('codigo');
            $table->string('nombre');
            $table->string('correo')->nullable();
            $table->string('celular', 50)->nullable();
        });

        $this->master('grupos_clientes', ['codigo'], fn (Blueprint $table) => $this->catalog($table));

        $this->master('condiciones_pago', ['codigo'], function (Blueprint $table) {
            $table->integer('codigo');
            $table->string('nombre');
            $table->integer('dias_extra')->nullable();
            $table->integer('meses_extra')->nullable();
        });

        $this->master('municipios', ['codigo'], function (Blueprint $table) {
            $table->string('codigo', 50);
            $table->string('nombre');
        });
    }

    public function down(): void
    {
        foreach (array_reverse(self::TABLES) as $table) {
            Schema::dropIfExists($table);
        }
    }

    private const TABLES = [
        'clientes', 'proveedores', 'direcciones', 'contactos', 'articulos', 'grupos_articulos',
        'marcas', 'precios', 'vendedores', 'grupos_clientes', 'condiciones_pago', 'municipios',
    ];

    /**
     * A master table: the part columns plus what every master row carries.
     *
     * @param  list<string>  $key
     */
    private function master(string $name, array $key, Closure $columns): void
    {
        Schema::create($name, function (Blueprint $table) use ($name, $key, $columns) {
            $table->id();
            // SGX or SDC.
            $table->string('empresa', 3);
            $columns($table);

            // SAP keys are case-sensitive; MySQL's default collation would
            // fold "C001" and "c001" (or "Bodega" and "BODEGA") into one row.
            if (Schema::getConnection()->getDriverName() === 'mysql') {
                foreach ($table->getColumns() as $column) {
                    if (in_array($column->get('name'), $key, true) && $column->get('type') === 'string') {
                        $column->collation('utf8mb4_bin');
                    }
                }
            }

            // False once SAP inactivates the row or a full run stops bringing it.
            $table->boolean('activo')->default(true);
            // Last change in SAP; only customers, suppliers and items bring it.
            $table->dateTime('actualizado_en_sap')->nullable();
            // When a closed run last wrote or inactivated the row.
            $table->dateTime('sincronizado_en');
            // The run (bases_sap) that last wrote the row. Not shown in the views.
            $table->unsignedBigInteger('corrida_id')->nullable();

            $table->unique(['empresa', ...$key]);

            // Contacts are refreshed by business partner; addresses already
            // have that prefix in their unique key.
            if ($name === 'contactos') {
                $table->index(['empresa', 'codigo_socio']);
            }
        });
    }

    /**
     * OCRD columns, shared by customers and suppliers.
     */
    private function businessPartner(Blueprint $table): void
    {
        $table->string('codigo', 50);
        $table->string('nombre');
        $table->string('nombre_extranjero')->nullable();
        $table->string('nit', 50)->nullable();
        $table->integer('grupo_codigo')->nullable();
        $table->integer('vendedor_codigo')->nullable();
        $table->integer('condicion_pago_codigo')->nullable();
        $table->integer('lista_precios_codigo')->nullable();
        $table->string('telefono', 50)->nullable();
        $table->string('telefono_2', 50)->nullable();
        $table->string('celular', 50)->nullable();
        $table->string('correo')->nullable();
        $table->string('ciudad')->nullable();
        $table->decimal('limite_credito', 19, 2)->nullable();
        $table->string('socio_vinculado', 50)->nullable();
        $table->date('creado_en_sap')->nullable();
    }

    /**
     * A catalog: an integer code and a name.
     */
    private function catalog(Blueprint $table): void
    {
        $table->integer('codigo');
        $table->string('nombre');
    }
};
