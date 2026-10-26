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
use Illuminate\Database\UniqueConstraintViolationException;
use LogicException;

/**
 * Opens a run (docs/contrato-robot.md, section 4.1): one dataset of one
 * company, with each part and its mode. At most one run per dataset and
 * company is open; an idle one expires first instead of blocking.
 */
final class StartRun
{
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
            $this->fail('conjunto', 'Conjunto desconocido: solo MAESTROS o CARTERA.');
        }

        if ($company === null) {
            $this->fail('empresa', 'Empresa desconocida: solo SGX o SDC.');
        }

        if ($type === null) {
            $this->fail('tipo', 'Tipo desconocido: solo completa o solicitud.');
        }

        $parts = $dataset ? $this->parts($input['partes'] ?? null, $dataset, $type) : [];
        $requests = $this->requests($input['solicitudes'] ?? []);
        $cutOff = $dataset ? $this->cutOff($input['fecha_corte'] ?? null, $dataset) : null;
        $extractedAt = SapTime::parse($input['extraida_en'] ?? null);

        if ($extractedAt === null) {
            $this->fail('extraida_en', 'Debe ser una hora ISO 8601 con zona.');
        }

        if ($dataset !== null && $company !== null && $requests !== []) {
            $this->checkRequests($requests, $dataset, $company, $parts);
        }

        if ($this->errors !== [] || $dataset === null || $company === null || $type === null || $extractedAt === null) {
            throw RobotRequestRejected::invalid('La corrida no cumple el contrato.', $this->errors);
        }

        $this->expireIdleRun($dataset, $company);

        $attributes = [
            'conjunto' => $dataset,
            'empresa' => $company,
            'tipo' => $type,
            'partes' => $parts,
            'solicitudes' => $requests,
            'fecha_corte' => $cutOff,
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
    private function parts(mixed $parts, Dataset $dataset, ?RunType $type): array
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
            } elseif ($mode === PartMode::Changes && ($type === RunType::Full || ! $part->tracksSapUpdates() && ! in_array($part, [Part::Addresses, Part::Contacts], true))) {
                // Only parts with an SAP update time (and the addresses and
                // contacts that follow their partner) can bring changes.
                $this->fail("partes.{$name}", $type === RunType::Full
                    ? 'En una corrida completa todas las partes van en modo todo.'
                    : 'Esta parte siempre llega en modo todo.');
            } else {
                $valid[$part->value] = $mode->value;
            }
        }

        if ($type === RunType::Full && array_diff(array_map(fn (Part $part): string => $part->value, Part::forDataset($dataset)), array_keys($parts)) !== []) {
            $this->fail('partes', 'Una corrida completa trae todas las partes del conjunto.');
        }

        return $valid;
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
            $asked = $request === null ? [] : array_map(fn (Part $part): string => $part->value, RequestScope::partsFor($request->conjunto, $request->parte));

            // A request already linked belongs to another open run.
            if ($request === null || $request->estado !== RequestState::Taken || $request->run_id !== null || $request->empresa !== $company
                || $request->conjunto !== $dataset || array_diff($asked, array_keys($parts)) !== []) {
                $this->fail('solicitudes', "La solicitud {$id} no está tomada, ya está en otra corrida, es de otra empresa o conjunto, o pide partes que la corrida no trae.");
            }
        }
    }

    private function cutOff(mixed $date, Dataset $dataset): ?string
    {
        if ($dataset === Dataset::Maestros) {
            if ($date !== null) {
                $this->fail('fecha_corte', 'MAESTROS no lleva fecha de corte.');
            }

            return null;
        }

        if (! SapTime::isDate($date)) {
            $this->fail('fecha_corte', 'CARTERA lleva fecha de corte AAAA-MM-DD.');

            return null;
        }

        return $date;
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
