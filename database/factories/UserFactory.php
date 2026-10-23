<?php

namespace Database\Factories;

use App\Models\User;
use App\Modules\Core\Contracts\Enums\Role;
use Illuminate\Database\Eloquent\Factories\Factory;
use Illuminate\Support\Str;

/**
 * An active user without a role who has not signed in with Microsoft yet.
 *
 * @extends Factory<User>
 */
class UserFactory extends Factory
{
    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'name' => fake()->name(),
            'email' => fake()->unique()->safeEmail(),
            'microsoft_id' => null,
            'role' => null,
            'is_active' => true,
            'remember_token' => Str::random(10),
        ];
    }

    public function adminTi(): static
    {
        return $this->state(['role' => Role::AdminTi]);
    }

    public function consulta(): static
    {
        return $this->state(['role' => Role::Consulta]);
    }

    public function inactive(): static
    {
        return $this->state(['is_active' => false]);
    }
}
