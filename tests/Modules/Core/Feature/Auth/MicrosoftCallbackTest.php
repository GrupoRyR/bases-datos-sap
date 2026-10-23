<?php

use App\Models\User;
use App\Modules\Core\Contracts\Enums\Role;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Exceptions;
use Laravel\Socialite\Two\InvalidStateException;
use Tests\Modules\Core\Support\FakeIdentityProvider;

const MICROSOFT_CALLBACK = '/auth/microsoft/callback?code=codigo-de-prueba&state=estado-de-prueba';

const REJECTED_MESSAGE = 'No puedes entrar con esa cuenta. Si crees que es un error, habla con TI.';

/**
 * The audit entries in order, as action => context (decoded), plus user_id.
 *
 * @return list<array{action: string, user_id: int|null, context: array<string, mixed>|null}>
 */
function signInAudit(): array
{
    return DB::table('audit_logs')->orderBy('id')->get()->map(fn (object $row): array => [
        'action' => $row->action,
        'user_id' => $row->user_id === null ? null : (int) $row->user_id,
        'context' => $row->context === null ? null : json_decode((string) $row->context, true),
    ])->all();
}

/**
 * Asserts the callback sends the guest back to /login with the one message
 * every rejection shows, and audits the rejection $reason for $email only.
 */
function assertSignInRejected(string $reason, string $email = 'ana.gomez@segurex.com'): void
{
    test()->get(MICROSOFT_CALLBACK)->assertRedirect('/login')->assertSessionHas('error', REJECTED_MESSAGE);
    test()->assertGuest();

    expect(signInAudit())->toBe([[
        'action' => 'core.auth.rejected',
        'user_id' => null,
        'context' => ['reason' => $reason, 'email' => $email],
    ]]);
}

beforeEach(function () {
    config(['services.microsoft.tenant' => FakeIdentityProvider::TENANT, 'core.admins' => ['ti@segurex.com']]);
    $this->microsoft = FakeIdentityProvider::install($this->app);
});

describe('a successful sign-in', function () {
    it('creates a new user without a role, signs them in and sends them to ask for access', function () {
        $this->freezeSecond();
        $this->microsoft->signsIn(FakeIdentityProvider::identity('Ana.Gomez@Segurex.com', 'oid-ana', name: 'Ana Gómez'));

        $this->get(MICROSOFT_CALLBACK)->assertRedirect('/');

        $user = User::query()->sole();

        expect($user->email)->toBe('ana.gomez@segurex.com')
            ->and($user->name)->toBe('Ana Gómez')
            ->and($user->microsoft_id)->toBe('oid-ana')
            ->and($user->role)->toBeNull()
            ->and($user->is_active)->toBeTrue()
            ->and($user->last_signed_in_at?->equalTo(now()))->toBeTrue()
            ->and(signInAudit())->toBe([
                ['action' => 'core.user.created', 'user_id' => null, 'context' => ['email' => 'ana.gomez@segurex.com', 'source' => 'microsoft']],
                ['action' => 'core.auth.signed_in', 'user_id' => $user->id, 'context' => ['method' => 'microsoft']],
            ]);

        $this->assertAuthenticatedAs($user);

        $this->followingRedirects()->get('/')->assertOk()->assertSee('Todavía no tienes acceso');
    });

    it('starts a new session', function () {
        $this->microsoft->signsIn(FakeIdentityProvider::identity());
        $before = session()->getId();

        $this->get(MICROSOFT_CALLBACK);

        expect(session()->getId())->not->toBe($before);
    });

    it('returns to the page the user asked for before signing in', function () {
        $this->get('/sin-acceso')->assertRedirect('/login');
        $this->microsoft->signsIn(FakeIdentityProvider::identity());

        $this->get(MICROSOFT_CALLBACK)->assertRedirect('/sin-acceso');
    });

    it('makes a bootstrap admin admin TI on their first sign-in', function () {
        $this->microsoft->signsIn(FakeIdentityProvider::identity('TI@segurex.com', 'oid-ti', name: 'TI'));

        $this->get(MICROSOFT_CALLBACK)->assertRedirect('/');

        $user = User::query()->sole();

        expect($user->role)->toBe(Role::AdminTi)
            ->and(array_column(signInAudit(), 'action'))->toBe(['core.user.created', 'core.user.role_changed', 'core.auth.signed_in'])
            ->and(signInAudit()[1]['context'])->toBe(['old' => null, 'new' => 'admin_ti', 'source' => 'core_admin_emails']);

        $this->followingRedirects()->get('/')->assertOk()->assertSee('Admin TI');
    });

    it('raises a registered bootstrap admin to admin TI', function () {
        $user = User::factory()->consulta()->create(['email' => 'ti@segurex.com', 'microsoft_id' => 'oid-ti']);
        $this->microsoft->signsIn(FakeIdentityProvider::identity('ti@segurex.com', 'oid-ti'));

        $this->get(MICROSOFT_CALLBACK)->assertRedirect('/');

        expect($user->refresh()->role)->toBe(Role::AdminTi)
            ->and(signInAudit()[0]['context'])->toBe(['old' => 'consulta', 'new' => 'admin_ti', 'source' => 'core_admin_emails']);
    });

    it('never downgrades anyone who is not a bootstrap admin', function () {
        $user = User::factory()->adminTi()->create(['email' => 'ana.gomez@segurex.com', 'microsoft_id' => 'oid-ana']);
        $this->microsoft->signsIn(FakeIdentityProvider::identity());

        $this->get(MICROSOFT_CALLBACK)->assertRedirect('/');

        expect($user->refresh()->role)->toBe(Role::AdminTi)
            ->and(array_column(signInAudit(), 'action'))->toBe(['core.auth.signed_in']);
    });

    it('recognizes a registered user by Microsoft id, even after an e-mail change', function () {
        $user = User::factory()->consulta()->create(['email' => 'ana.antes@segurex.com', 'microsoft_id' => 'oid-ana', 'name' => 'Ana']);
        $this->microsoft->signsIn(FakeIdentityProvider::identity('ana.gomez@segurex.com', 'oid-ana', name: 'Ana María Gómez'));

        $this->get(MICROSOFT_CALLBACK)->assertRedirect('/');

        expect(User::query()->count())->toBe(1)
            ->and($user->refresh()->name)->toBe('Ana María Gómez')
            ->and($user->last_signed_in_at)->not->toBeNull()
            ->and(array_column(signInAudit(), 'action'))->toBe(['core.auth.signed_in']);

        $this->assertAuthenticatedAs($user);
    });

    it('recognizes a registered user by e-mail in any case and links their Microsoft account', function () {
        $user = User::factory()->consulta()->create(['email' => 'ana.gomez@segurex.com', 'name' => 'Ana']);
        $this->microsoft->signsIn(FakeIdentityProvider::identity('ANA.Gomez@Segurex.com', 'oid-ana', name: 'Ana Gómez'));

        $this->get(MICROSOFT_CALLBACK)->assertRedirect('/');

        expect(User::query()->count())->toBe(1)
            ->and($user->refresh()->microsoft_id)->toBe('oid-ana')
            ->and($user->name)->toBe('Ana Gómez')
            ->and($user->role)->toBe(Role::Consulta);

        $this->assertAuthenticatedAs($user);
        $this->followingRedirects()->get('/')->assertOk()->assertSee('Hola, Ana Gómez')->assertSee('Consulta');
    });
});

describe('a rejected sign-in', function () {
    it('refuses accounts of another directory', function (?string $tenant) {
        $this->microsoft->signsIn(FakeIdentityProvider::identity(tenantId: $tenant));

        assertSignInRejected('tenant');

        expect(User::query()->count())->toBe(0);
    })->with([
        'another tenant' => ['99999999-0000-0000-0000-000000000000'],
        'no tid claim' => [null],
        'empty tid claim' => [''],
    ]);

    it('compares tenant ids without regard to case', function () {
        $this->microsoft->signsIn(FakeIdentityProvider::identity(tenantId: strtoupper(FakeIdentityProvider::TENANT)));

        $this->get(MICROSOFT_CALLBACK)->assertRedirect('/');

        $this->assertAuthenticated();
    });

    it('refuses everyone while no tenant is configured', function (?string $configured) {
        config(['services.microsoft.tenant' => $configured]);
        $this->microsoft->signsIn(FakeIdentityProvider::identity(tenantId: $configured));

        assertSignInRejected('tenant');
    })->with(['null' => [null], 'empty' => [''], 'spaces' => ['  ']]);

    it('keeps a deactivated user out, untouched', function () {
        $user = User::factory()->adminTi()->inactive()->create(['email' => 'ana.gomez@segurex.com', 'name' => 'Ana']);
        $this->microsoft->signsIn(FakeIdentityProvider::identity(name: 'Ana Gómez'));

        assertSignInRejected('inactive');

        expect($user->refresh()->microsoft_id)->toBeNull()
            ->and($user->name)->toBe('Ana')
            ->and($user->last_signed_in_at)->toBeNull();
    });

    it('refuses an e-mail registered with another Microsoft account', function () {
        $user = User::factory()->create(['email' => 'ana.gomez@segurex.com', 'microsoft_id' => 'oid-otra']);
        $this->microsoft->signsIn(FakeIdentityProvider::identity('ana.gomez@segurex.com', 'oid-ana'));

        assertSignInRejected('identity_mismatch');

        expect($user->refresh()->microsoft_id)->toBe('oid-otra');
    });

    it('refuses a Microsoft account that belongs to another user', function () {
        $owner = User::factory()->create(['email' => 'ana.antes@segurex.com', 'microsoft_id' => 'oid-ana']);
        $other = User::factory()->create(['email' => 'ana.gomez@segurex.com']);
        $this->microsoft->signsIn(FakeIdentityProvider::identity('ana.gomez@segurex.com', 'oid-ana'));

        assertSignInRejected('identity_mismatch');

        expect($owner->refresh()->email)->toBe('ana.antes@segurex.com')
            ->and($other->refresh()->microsoft_id)->toBeNull();
    });
});

it('reports a failure of Microsoft and asks the user to try again', function () {
    Exceptions::fake();
    $this->microsoft->fails(new InvalidStateException);

    $this->get(MICROSOFT_CALLBACK)
        ->assertRedirect('/login')
        ->assertSessionHas('error', 'No pudimos completar el ingreso con Microsoft. Inténtalo de nuevo.');

    $this->assertGuest();
    Exceptions::assertReported(InvalidStateException::class);
    expect(User::query()->count())->toBe(0);
});

it('sends signed-in users home without asking Microsoft', function () {
    $this->actingAs(User::factory()->consulta()->create())->get(MICROSOFT_CALLBACK)->assertRedirect('/');
});
