<?php

namespace App\Support\Navigation;

use Illuminate\Contracts\Auth\Authenticatable;
use Illuminate\Support\Facades\Gate;
use Illuminate\Support\Facades\Route;
use InvalidArgumentException;

/**
 * Navigation shared by every module (docs/arquitectura.md). Bound as a
 * singleton; modules fill it from their provider's navigation() hook and
 * the layouts read it per user.
 */
final class NavRegistry
{
    /** @var array<string, NavItem> */
    private array $items = [];

    /**
     * Adds items atomically: a duplicate key rejects the whole call.
     *
     * @throws InvalidArgumentException
     */
    public function add(NavItem ...$items): void
    {
        $keys = [];

        foreach ($items as $item) {
            if ($this->has($item->key) || isset($keys[$item->key])) {
                throw new InvalidArgumentException("The navigation item [{$item->key}] is already registered.");
            }

            $keys[$item->key] = true;
        }

        foreach ($items as $item) {
            $this->items[$item->key] = $item;
        }
    }

    public function has(string $key): bool
    {
        return isset($this->items[$key]);
    }

    /**
     * Every item, by order and then by label.
     *
     * @return list<NavItem>
     */
    public function all(): array
    {
        $items = array_values($this->items);

        usort($items, fn (NavItem $a, NavItem $b): int => $a->order <=> $b->order ?: strcmp($a->label, $b->label));

        return $items;
    }

    /**
     * Items the user may open: guests see nothing, items whose route is not
     * registered are skipped and permissions are checked with the Gate.
     *
     * @return list<NavItem>
     */
    public function visibleTo(?Authenticatable $user): array
    {
        if ($user === null) {
            return [];
        }

        $gate = Gate::forUser($user);

        return array_values(array_filter(
            $this->all(),
            fn (NavItem $item): bool => Route::has($item->route)
                && ($item->permission === null || $gate->allows($item->permission)),
        ));
    }

    /**
     * Visible items by group, with groups in the order of their first item.
     *
     * @return array<string, list<NavItem>>
     */
    public function groupedFor(?Authenticatable $user): array
    {
        return self::group($this->visibleTo($user));
    }

    /**
     * Visible items of the phone bottom bar.
     *
     * @return list<NavItem>
     */
    public function mobileFor(?Authenticatable $user): array
    {
        return self::mobileOnly($this->visibleTo($user));
    }

    /**
     * groupedFor() and mobileFor() from a single visibility pass, so each
     * route and permission is checked once per page.
     *
     * @return array{groups: array<string, list<NavItem>>, mobile: list<NavItem>}
     */
    public function menuFor(?Authenticatable $user): array
    {
        $visible = $this->visibleTo($user);

        return ['groups' => self::group($visible), 'mobile' => self::mobileOnly($visible)];
    }

    /**
     * @param  list<NavItem>  $items
     * @return array<string, list<NavItem>>
     */
    private static function group(array $items): array
    {
        $groups = [];

        foreach ($items as $item) {
            $groups[$item->group][] = $item;
        }

        return $groups;
    }

    /**
     * @param  list<NavItem>  $items
     * @return list<NavItem>
     */
    private static function mobileOnly(array $items): array
    {
        return array_values(array_filter($items, fn (NavItem $item): bool => $item->mobile));
    }
}
