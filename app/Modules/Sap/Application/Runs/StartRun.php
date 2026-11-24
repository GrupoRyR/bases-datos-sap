<?php

namespace App\Modules\Sap\Application\Runs;

use App\Modules\Sap\Contracts\Enums\Company;
use App\Modules\Sap\Contracts\Enums\Dataset;
use App\Modules\Sap\Contracts\Enums\Part;
use App\Modules\Sap\Contracts\Enums\RequestScope;
use App\Modules\Sap\Contracts\Enums\RequestState;
use App\Modules\Sap\Domain\Runs\PartMode;
use App\Modules\Sap\Domain\Runs\RunState;
use App\Modules\Sap\Domain\Runs\RunType;
use App\Modules\Sap\Domain\Values\SapTime;
use App\Modules\Sap\Http\Exceptions\RobotRequestRejected;
use App\Modules\Sap\Models\Run;
use App\Modules\Sap\Models\UpdateRequest;
use Carbon\CarbonImmutable;
use Illuminate\Database\UniqueConstraintViolationException;
use Illuminate\Support\Facades\DB;
use LogicException;

/**
 * Opens a run (docs/contrato-robot.md, section 4.1): one dataset of one
 * company, with each part and its mode. At most one run per dataset and
 * company is open; an idle one expires first instead of blocking.
 */
final class StartRun
{
    /** The earliest VENTAS window start accepted, in days before today (the formula reaches 37). */
    private const WINDOW_MAX_DAYS = 40;

    /** The earliest PRODUCCION window start, so the initial load can reach back months (contract section 12.3). */
    private const PRODUCTION_WINDOW_FROM = '2026-01-01';

    /** @var array<string, string> */
    private array $errors = [];

    /**
     * @param  array<string, mixed>  $input
     */
    public function handle(array $input, string $robotKey): Run
    {
        $this->errors = [];

        $dataset = Dataset::tryFrom(is_string($input['conjunto'] ?? null) ? $input['conjunto'] : '');
        $company = Company::tryFrom(is_string($input['empresa'] ?? null) ? $input['empresa'] : '');
        $type = RunType::tryFrom(is_string($input['tipo'] ?? null) ? $input['tipo'] : '');

        if ($dataset === null) {
            $this->fail('conjunto', 'Conjunto desconocido: solo MAESTROS, CARTERA, VENTAS, PEDIDOS o PRODUCCION.');
        }

        if ($company === null) {
            $this->fail('empresa', 'Empresa desconocida: solo SGX o SDC.');
        } elseif ($dataset !== null && ! in_array($company, $dataset->companies(), true)) {
            $this->fail('empresa', "{$dataset->value} es solo de ".implode(' y ', array_map(fn (Company $only): string => $only->value, $dataset->companies())).'.');
        }

        if ($type === null) {
            $this->fail('tipo', 'Tipo desconocido: solo completa, solicitud o historico.');
        } elseif ($type === RunType::Historical && $dataset !== null && $dataset !== Dataset::Ventas) {
            $this->fail('tipo', 'Solo VENTAS tiene corridas historico.');
        }

        $parts = $dataset ? $this->parts($input['partes'] ?? null, $dataset, $type, $company) : [];
        $requests = $this->requests($input['solicitudes'] ?? []);
        $cutOff = $dataset ? $this->cutOff($input['fecha_corte'] ?? null, $dataset) : null;
        $window = $dataset ? $this->window($input['ventana_desde'] ?? null, $dataset, $type) : null;
        $until = $this->until($input['ventana_hasta'] ?? null, $type, $window);
        $extractedAt = SapTime::parse($input['extraida_en'] ?? null);

        if ($extractedAt === null) {
            $this->fail('extraida_en', 'Debe ser una hora ISO 8601 con zona.');
        }

        if ($type === RunType::Historical && $requests !== []) {
            $this->fail('solicitudes', 'Una corrida historico no atiende solicitudes.');
        }

        if ($dataset !== null && $company !== null && $requests !== []) {
            $this->checkRequests($requests, $dataset, $company, $parts);
        }

        if ($this->errors !== [] || $dataset === null || $company === null || $type === null || $extractedAt === null) {
            throw RobotRequestRejected::invalid('La corrida no cumple el contrato.', $this->errors);
        }

        if ($type === RunType::Historical && $window !== null && $until !== null) {
            $this->refuseLoadedRange($company, $window, $until);
        }

        $this->expireIdleRun($dataset, $company);

        $attributes = [
            'conjunto' => $dataset,
            'empresa' => $company,
            'tipo' => $type,
            'partes' => $parts,
            'solicitudes' => $requests,
            'fecha_corte' => $cutOff,
            'ventana_desde' => $window,
            'ventana_hasta' => $until,
            'extraida_en' => $extractedAt,
            'estado' => RunState::Open,
            'abierta_lock' => Run::lockFor($dataset, $company),
            'robot_key' => $robotKey,
        ];

        // The second try covers the run holding the lock finishing between
        // the refused insert and the lookup.
        foreach ([1, 2] as $attempt) {
            try {
                $run = Run::create([...$attributes, 'abierta_hasta' => now()->addMinutes(Run::IDLE_MINUTES)]);
                UpdateRequest::whereIn('id', $requests)->update(['run_id' => $run->id]);

                return $run;
            } catch (UniqueConstraintViolationException) {
                $open = Run::where('abierta_lock', $attributes['abierta_lock'])->first();

                if ($open !== null || $attempt === 2) {
                    throw new RobotRequestRejected(409, 'Ya hay una corrida abierta de ese conjunto y empresa.', ['run_id' => $open?->id]);
                }
            }
        }

        throw new LogicException('Unreachable: every attempt returns or throws.');
    }

    /**
     * @return array<string, string> Each part and its mode.
     */
    private function parts(mixed $parts, Dataset $dataset, ?RunType $type, ?Company $company): array
    {
        if (! is_array($parts) || $parts === [] || array_is_list($parts)) {
            $this->fail('partes', 'Debe traer al menos una parte con su modo.');

            return [];
        }

        $valid = [];

        foreach ($parts as $name => $mode) {
            $part = Part::tryFrom((string) $name);
            $mode = PartMode::tryFrom(is_string($mode) ? $mode : '');

            if ($part === null || $part->dataset() !== $dataset) {
                $this->fail("partes.{$name}", "Parte desconocida en {$dataset->value}.");
            } elseif ($mode === null) {
                $this->fail("partes.{$name}", 'Modo desconocido: solo todo o cambios.');
            } elseif ($mode === PartMode::Changes && ($type?->isWhole() || ! $part->tracksSapUpdates() && ! in_array($part, [Part::Addresses, Part::Contacts], true))) {
                // Only parts with an SAP update time (and the addresses and
                // contacts that follow their partner) can bring changes.
                $this->fail("partes.{$name}", $type?->isWhole()
                    ? 'En una corrida completa o historico todas las partes van en modo todo.'
                    : 'Esta parte siempre llega en modo todo.');
            } else {
                $valid[$part->value] = $mode->value;
            }
        }

        if ($type?->isWhole() && array_diff($this->required($dataset, $company), array_keys($parts)) !== []) {
            $this->fail('partes', 'Una corrida completa o historico trae todas las partes del conjunto.');
        }

        return $valid;
    }

    /**
     * The parts a full run must bring: all of the dataset's, except those the
     * company has no data for (Derivados has no public price list).
     *
     * @return list<string>
     */
    private function required(Dataset $dataset, ?Company $company): array
    {
        $omittable = $this->omittable($company);

        return array_values(array_map(
            fn (Part $part): string => $part->value,
            array_filter(Part::forDataset($dataset), fn (Part $part): bool => ! in_array($part, $omittable, true)),
        ));
    }

    /**
     * Parts a company may leave out of a full run (docs/contrato-robot.md, section 4.1).
     * Leaving one out changes nothing for it: no rows are inactivated.
     *
     * @return list<Part>
     */
    private function omittable(?Company $company): array
    {
        return $company === Company::Sdc ? [Part::Prices] : [];
    }

    /**
     * @return list<int>
     */
    private function requests(mixed $requests): array
    {
        if (! is_array($requests) || ! array_is_list($requests) || array_filter($requests, fn (mixed $id): bool => ! is_int($id) || $id < 1) !== []) {
            $this->fail('solicitudes', 'Debe ser una lista de ids de solicitudes.');

            return [];
        }

        return $requests;
    }

    /**
     * Every request the run serves must be taken, of the same company and
     * dataset, and ask only for parts the run brings (contract section 4.1).
     *
     * @param  list<int>  $ids
     * @param  array<string, string>  $parts
     */
    private function checkRequests(array $ids, Dataset $dataset, Company $company, array $parts): void
    {
        $found = UpdateRequest::whereIn('id', $ids)->get()->keyBy('id');

        foreach ($ids as $id) {
            $request = $found->get($id);
            $askedParts = $request === null ? [] : RequestScope::partsFor($request->conjunto, $request->parte);
            // A request for the whole dataset does not need the parts the company may omit;
            // one for just those parts still does, so it is answered (the robot fails it).
            $omitted = $request?->parte === null ? $this->omittable($company) : [];
            $asked = array_values(array_map(
                fn (Part $part): string => $part->value,
                array_filter($askedParts, fn (Part $part): bool => ! in_array($part, $omitted, true)),
            ));

            // A request already linked belongs to another open run.
            if ($request === null || $request->estado !== RequestState::Taken || $request->run_id !== null || $request->empresa !== $company
                || $request->conjunto !== $dataset || array_diff($asked, array_keys($parts)) !== []) {
                $this->fail('solicitudes', "La solicitud {$id} no está tomada, ya está en otra corrida, es de otra empresa o conjunto, o pide partes que la corrida no trae.");
            }
        }
    }

    private function cutOff(mixed $date, Dataset $dataset): ?string
    {
        if ($dataset !== Dataset::Cartera) {
            if ($date !== null) {
                $this->fail('fecha_corte', "{$dataset->value} no lleva fecha de corte.");
            }

            return null;
        }

        if (! SapTime::isDate($date)) {
            $this->fail('fecha_corte', 'CARTERA lleva fecha de corte AAAA-MM-DD.');

            return null;
        }

        return $date;
    }

    /**
     * The first day of the window of VENTAS or PRODUCCION (contract sections
     * 4.1, 10.1 and 12.3), computed by the robot in HANA, up to tomorrow,
     * today in Bogota. VENTAS reaches back 40 days at most, so a robot error
     * never reaches closed months; PRODUCCION, to 2026-01-01, since all of it
     * comes again from SAP. The other datasets have no window. A historical
     * run starts on the first day of a month instead (section 10.4).
     */
    private function window(mixed $date, Dataset $dataset, ?RunType $type): ?string
    {
        if (! in_array($dataset, [Dataset::Ventas, Dataset::Produccion], true)) {
            if ($date !== null) {
                $this->fail('ventana_desde', 'Solo VENTAS y PRODUCCION llevan ventana_desde.');
            }

            return null;
        }

        if (! SapTime::isDate($date)) {
            $this->fail('ventana_desde', "{$dataset->value} lleva ventana_desde AAAA-MM-DD.");

            return null;
        }

        if ($type === RunType::Historical) {
            if (substr($date, 8) !== '01') {
                $this->fail('ventana_desde', 'En una corrida historico es el primer día de un mes.');

                return null;
            }

            return $date;
        }

        $today = CarbonImmutable::now((string) config('app.timezone'));
        [$earliest, $message] = $dataset === Dataset::Ventas
            ? [$today->subDays(self::WINDOW_MAX_DAYS)->toDateString(), 'Debe estar entre hoy menos '.self::WINDOW_MAX_DAYS.' días y mañana.']
            : [self::PRODUCTION_WINDOW_FROM, 'Debe estar entre '.self::PRODUCTION_WINDOW_FROM.' y mañana.'];

        if ($date > $today->addDay()->toDateString() || $date < $earliest) {
            $this->fail('ventana_desde', $message);

            return null;
        }

        return $date;
    }

    /**
     * The last day of a historical run (contract section 10.4): in the month
     * of ventana_desde and before the nightly window starts today, so the
     * load never meets the 02:00 run. Any other run carries none.
     */
    private function until(mixed $date, ?RunType $type, ?string $from): ?string
    {
        if ($type !== RunType::Historical) {
            if ($date !== null) {
                $this->fail('ventana_hasta', 'Solo una corrida historico lleva ventana_hasta.');
            }

            return null;
        }

        if (! SapTime::isDate($date)) {
            $this->fail('ventana_hasta', 'Una corrida historico lleva ventana_hasta AAAA-MM-DD.');

            return null;
        }

        $nightly = self::nightlyWindowStart();

        if ($from !== null && ($date < $from || substr($date, 0, 7) !== substr($from, 0, 7))) {
            $this->fail('ventana_hasta', 'Debe estar en el mismo mes de ventana_desde, desde ese día.');
        } elseif ($date >= $nightly) {
            $this->fail('ventana_hasta', "Debe ser anterior al inicio de la ventana nocturna ({$nightly}).");
        } else {
            return $date;
        }

        return null;
    }

    /**
     * The day the nightly window starts today, with the formula of contract
     * section 10.1 (ADD_DAYS(CURRENT_DATE, -6 - DAYOFMONTH(CURRENT_DATE)))
     * and today in Bogota.
     */
    private static function nightlyWindowStart(): string
    {
        $today = CarbonImmutable::now((string) config('app.timezone'))->startOfDay();

        return $today->subDays(6 + $today->day)->toDateString();
    }

    /**
     * A historical run only loads an empty range: if the company has any
     * VENTAS line in it, 409 and nothing opens (contract section 10.4).
     */
    private function refuseLoadedRange(Company $company, string $from, string $until): void
    {
        $loaded = DB::connection(Dataset::Ventas->connection())->table(Part::Sales->table())
            ->where('empresa', $company->value)
            ->whereBetween('fecha_contabilizacion', [$from, $until])
            ->exists();

        if ($loaded) {
            throw new RobotRequestRejected(409, "La empresa ya tiene ventas entre {$from} y {$until}: ese rango no se vuelve a cargar.");
        }
    }

    private function expireIdleRun(Dataset $dataset, Company $company): void
    {
        Run::where('abierta_lock', Run::lockFor($dataset, $company))->first()?->expireIfIdle();
    }

    private function fail(string $field, string $message): void
    {
        $this->errors[$field] ??= $message;
    }
}
