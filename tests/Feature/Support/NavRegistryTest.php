<?php

use App\Models\User;
use App\Support\Navigation\NavItem;
use App\Support\Navigation\NavRegistry;
use Illuminate\Support\Facades\Gate;
use Illuminate\Support\Facades\Route;

beforeEach(function () {
    Route::get('/nav/a', fn () => 'a')->name('nav.a');
    Route::get('/nav/b', fn () => 'b')->name('nav.b');
    Route::getRoutes()->refreshNameLookups();

    $this->navigation = new NavRegistry;
});

it('is shared by every module', function () {
    expect(app(NavRegistry::class))->toBe(app(NavRegistry::class));
});

it('rejects a duplicate key without adding any item of the call', function () {
    $this->navigation->add(new NavItem(key: 'a', label: 'A', route: 'nav.a'));

    expect(fn () => $this->navigation->add(
        new NavItem(key: 'b', label: 'B', route: 'nav.b'),
        new NavItem(key: 'a', label: 'Otra A', route: 'nav.a'),
    ))->toThrow(InvalidArgumentException::class);

    expect($this->navigation->has('b'))->toBeFalse();
});

it('sorts items by order and then by label', function () {
    $this->navigation->add(
        new NavItem(key: 'z', label: 'Zeta', route: 'nav.a', order: 10),
        new NavItem(key: 'c', label: 'Ce', route: 'nav.a', order: 20),
        new NavItem(key: 'a', label: 'A', route: 'nav.a', order: 20),
    );

    expect(array_map(fn (NavItem $item): string => $item->key, $this->navigation->all()))->toBe(['z', 'a', 'c']);
});

it('shows guests nothing and users only routed items they may open', function () {
    Gate::define('nav.manage', fn (User $user): bool => false);

    $this->navigation->add(
        new NavItem(key: 'a', label: 'A', route: 'nav.a', group: 'Uno', mobile: true),
        new NavItem(key: 'b', label: 'B', route: 'nav.b', permission: 'nav.manage'),
        new NavItem(key: 'x', label: 'X', route: 'nav.missing'),
    );

    $user = new User;
    $menu = $this->navigation->menuFor($user);

    expect($this->navigation->visibleTo(null))->toBe([])
        ->and(array_keys($menu['groups']))->toBe(['Uno'])
        ->and(array_map(fn (NavItem $item): string => $item->key, $menu['mobile']))->toBe(['a']);
});
