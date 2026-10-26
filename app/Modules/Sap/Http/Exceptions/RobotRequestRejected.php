<?php

namespace App\Modules\Sap\Http\Exceptions;

use Exception;
use Illuminate\Http\JsonResponse;

/**
 * A robot request the contract refuses (docs/contrato-robot.md): renders as
 * {"message": ..., ...extra} with its status, e.g. 422 with "errors" or 409
 * with "estado". The repository ships no Spanish validation messages, so
 * the module writes its own.
 */
final class RobotRequestRejected extends Exception
{
    /**
     * @param  array<string, mixed>  $extra
     */
    public function __construct(public readonly int $status, string $message, public readonly array $extra = [])
    {
        parent::__construct($message);
    }

    /**
     * 422 with up to 50 errors keyed by field, as the contract says.
     *
     * @param  array<string, string>  $errors
     */
    public static function invalid(string $message, array $errors): self
    {
        return new self(422, $message, ['errors' => array_map(
            fn (string $error): array => [$error],
            array_slice($errors, 0, 50, true),
        )]);
    }

    public function render(): JsonResponse
    {
        return response()->json(['message' => $this->getMessage(), ...$this->extra], $this->status);
    }
}
