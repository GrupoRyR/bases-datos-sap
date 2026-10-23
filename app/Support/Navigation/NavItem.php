<?php

namespace App\Support\Navigation;

use Closure;
use Illuminate\Http\Request;

/**
 * One entry of the sidebar (and, optionally, of the phone bottom bar).
 * Modules add theirs from the navigation() hook of their service provider.
 */
final readonly class NavItem
{
    /**
     * @param  string  $key  Unique key, e.g. "panel.inicio".
     * @param  string  $label  Spanish UI text, sentence case.
     * @param  string  $route  Route name the item links to.
     * @param  string|null  $icon  Icon name from the design system icon set.
     * @param  string|null  $permission  Ability checked with the Gate.
     * @param  string  $group  Sidebar section label.
     * @param  int  $order  Lower comes first; ties are sorted by label.
     * @param  string|null  $activePattern  routeIs() pattern that marks the item active; defaults to $route.
     * @param  bool  $mobile  Also shown in the phone bottom bar.
     * @param  (Closure(): (int|null))|null  $badge  Counter shown next to the label, e.g. pending replies.
     */
    public function __construct(
        public string $key,
        public string $label,
        public string $route,
        public ?string $icon = null,
        public ?string $permission = null,
        public string $group = 'General',
        public int $order = 100,
        public ?string $activePattern = null,
        public bool $mobile = false,
        public ?Closure $badge = null,
    ) {}

    public function url(): string
    {
        return route($this->route);
    }

    public function isActive(?Request $request = null): bool
    {
        $request ??= request();

        return $request->routeIs($this->activePattern ?? $this->route);
    }

    /**
     * Runs the badge callback; null means no badge.
     */
    public function badgeCount(): ?int
    {
        return $this->badge === null ? null : ($this->badge)();
    }
}
