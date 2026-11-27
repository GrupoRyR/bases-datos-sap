<?php

use Symfony\Component\Process\ExecutableFinder;
use Symfony\Component\Process\Process;

/*
|--------------------------------------------------------------------------
| deploy/despachar.sh
|--------------------------------------------------------------------------
|
| The dispatcher is the only entry point of the deploy key. Each test builds a
| throwaway fixture: a bare "origin", the "app" clone the dispatcher works on,
| and a "work" clone that pushes new commits to origin/main. PHP and the deploy
| script are stubs that log what they were asked to do, so nothing real runs.
|
*/

/**
 * Git for Windows' bin/bash.exe sets up the PATH (git, grep, cut…) for the
 * script; System32\bash.exe would be WSL, so it is never used.
 */
function dispatcherBash(): ?string
{
    if (PHP_OS_FAMILY !== 'Windows') {
        return (new ExecutableFinder)->find('bash');
    }

    $execPath = new Process(['git', '--exec-path']);
    $execPath->run();

    if (! $execPath->isSuccessful()) {
        return null;
    }

    $bash = dirname(trim($execPath->getOutput()), 3).'/bin/bash.exe';

    return is_file($bash) ? $bash : null;
}

/**
 * Isolates every git call (the fixture's and the dispatcher's) from the
 * machine's own git config: no signing, hooks or default branch leak in.
 *
 * @return array<string, string>
 */
function dispatcherGitEnv(string $root): array
{
    return [
        'GIT_CONFIG_GLOBAL' => "{$root}/gitconfig",
        'GIT_CONFIG_NOSYSTEM' => '1',
        'GIT_AUTHOR_NAME' => 'Fixture',
        'GIT_AUTHOR_EMAIL' => 'fixture@example.test',
        'GIT_COMMITTER_NAME' => 'Fixture',
        'GIT_COMMITTER_EMAIL' => 'fixture@example.test',
    ];
}

function dispatcherGit(string $root, string $cwd, string ...$args): string
{
    $process = new Process(['git', ...$args], $cwd, dispatcherGitEnv($root));
    $process->setTimeout(60);
    $process->mustRun();

    return trim($process->getOutput());
}

/**
 * Commits the given files in the work clone, pushes them to origin/main and
 * returns the new sha.
 *
 * @param  array<string, string>  $files
 */
function dispatcherPush(string $root, array $files, string $branch = 'main'): string
{
    $work = "{$root}/work";

    foreach ($files as $path => $contents) {
        if (! is_dir(dirname("{$work}/{$path}"))) {
            mkdir(dirname("{$work}/{$path}"), 0777, true);
        }

        file_put_contents("{$work}/{$path}", $contents);
    }

    dispatcherGit($root, $work, 'add', '--all');
    dispatcherGit($root, $work, 'commit', '--quiet', '--message', 'fixture '.count($files));
    dispatcherGit($root, $work, 'push', '--quiet', 'origin', "HEAD:{$branch}");

    return dispatcherGit($root, $work, 'rev-parse', 'HEAD');
}

/**
 * The stubs and a plain app folder: enough for the orders that never touch git.
 * Tests that need repositories call dispatcherRepos() first.
 *
 * @return array{root: string, app: string, bash: string, php: string, deploy: string, noop: string, log: string}
 */
function dispatcherFixture(string $bash): array
{
    $root = str_replace('\\', '/', sys_get_temp_dir()).'/despachar-'.bin2hex(random_bytes(6));
    mkdir($root);
    touch("{$root}/gitconfig");
    mkdir("{$root}/app/storage", 0777, true);

    // `$PHP artisan …`: logs its arguments and exits with STUB_PHP_EXIT.
    file_put_contents("{$root}/php-stub", <<<'BASH'
        #!/usr/bin/env bash
        printf '%s\n' "$*" >> "$STUB_LOG"
        printf 'php stub: %s\n' "$*"
        exit "${STUB_PHP_EXIT:-0}"

        BASH);
    chmod("{$root}/php-stub", 0755);

    // What deploy/deploy.sh does with DEPLOY_REF, without composer or artisan.
    file_put_contents("{$root}/deploy-stub", <<<'BASH'
        set -euo pipefail
        printf 'deploy %s\n' "$DEPLOY_REF" >> "$STUB_LOG"
        git fetch --quiet origin
        git merge --quiet --ff-only "$DEPLOY_REF"

        BASH);

    // A deploy that "succeeds" without moving HEAD.
    file_put_contents("{$root}/noop-deploy-stub", <<<'BASH'
        printf 'deploy %s\n' "$DEPLOY_REF" >> "$STUB_LOG"

        BASH);

    return [
        'root' => $root,
        'app' => "{$root}/app",
        'bash' => $bash,
        'php' => "{$root}/php-stub",
        'deploy' => "{$root}/deploy-stub",
        'noop' => "{$root}/noop-deploy-stub",
        'log' => "{$root}/stub.log",
    ];
}

/**
 * Replaces the plain app folder with a clone of a bare "origin" that has one
 * commit on main, plus the "work" clone that pushes the next ones.
 *
 * @param  array{root: string, app: string, bash: string, php: string, deploy: string, noop: string, log: string}  $fx
 */
function dispatcherRepos(array $fx): void
{
    $root = $fx['root'];
    dispatcherRemove($fx['app']);

    dispatcherGit($root, $root, 'init', '--quiet', '--bare', '--initial-branch=main', 'origin.git');
    dispatcherGit($root, $root, 'clone', '--quiet', "{$root}/origin.git", 'work');
    dispatcherGit($root, "{$root}/work", 'symbolic-ref', 'HEAD', 'refs/heads/main');
    dispatcherPush($root, [
        '.gitignore' => "/storage/\n/.env\n",
        'README.md' => "fixture\n",
        'database/migrations/0001_01_01_000000_create_users_table.php' => "<?php\n",
    ]);
    dispatcherGit($root, $root, 'clone', '--quiet', "{$root}/origin.git", 'app');

    mkdir("{$fx['app']}/storage/framework", 0777, true);
    mkdir("{$fx['app']}/storage/logs", 0777, true);
}

/**
 * Runs `bash deploy/despachar.sh` the way sshd does, with the order in
 * SSH_ORIGINAL_COMMAND.
 *
 * @param  array{root: string, app: string, bash: string, php: string, deploy: string, noop: string, log: string}  $fx
 * @param  array<string, string>  $env
 */
function dispatcherRun(array $fx, string $order, array $env = []): Process
{
    $process = new Process([$fx['bash'], 'deploy/despachar.sh'], base_path(), [
        ...dispatcherGitEnv($fx['root']),
        'SSH_ORIGINAL_COMMAND' => $order,
        'BASES_SAP_APP_DIR' => $fx['app'],
        'PHP' => $fx['php'],
        'DEPLOY_SCRIPT' => $fx['deploy'],
        'STUB_LOG' => $fx['log'],
        'STUB_PHP_EXIT' => '0',
        ...$env,
    ]);
    $process->setTimeout(60);
    $process->run();

    return $process;
}

/**
 * @param  array{root: string, app: string, bash: string, php: string, deploy: string, noop: string, log: string}  $fx
 */
function dispatcherHead(array $fx): string
{
    return dispatcherGit($fx['root'], $fx['app'], 'rev-parse', 'HEAD');
}

/**
 * @param  array{root: string, app: string, bash: string, php: string, deploy: string, noop: string, log: string}  $fx
 */
function dispatcherLog(array $fx): string
{
    return is_file($fx['log']) ? (string) file_get_contents($fx['log']) : '';
}

/** Git marks its objects read-only, which blocks unlink() on Windows. */
function dispatcherRemove(string $path): void
{
    if (is_link($path) || is_file($path)) {
        @chmod($path, 0666);
        unlink($path);

        return;
    }

    if (! is_dir($path)) {
        return;
    }

    foreach (scandir($path) ?: [] as $entry) {
        if ($entry !== '.' && $entry !== '..') {
            dispatcherRemove("{$path}/{$entry}");
        }
    }

    rmdir($path);
}

beforeEach(function () {
    $bash = dispatcherBash();

    if ($bash === null || (new ExecutableFinder)->find('git') === null) {
        $this->markTestSkipped('The dispatcher tests need bash and git.');
    }

    $this->fx = dispatcherFixture($bash);
});

afterEach(function () {
    if (isset($this->fx)) {
        dispatcherRemove($this->fx['root']);
    }
});

it('answers ping with ok', function () {
    $process = dispatcherRun($this->fx, 'ping');

    expect($process->getExitCode())->toBe(0)
        ->and($process->getOutput())->toBe("ok\n");
});

it('refuses anything outside the closed list without running it', function (string $order) {
    $process = dispatcherRun($this->fx, $order);

    expect($process->getExitCode())->toBe(64)
        ->and($process->getOutput())->toBe('')
        ->and($process->getErrorOutput())->toContain('order not allowed')
        ->and(dispatcherLog($this->fx))->toBe('');
})->with([
    'empty input' => [''],
    'unknown order' => ['reboot'],
    'uppercase' => ['PING'],
    'extra argument' => ['ping now'],
    'missing sha' => ['desplegar'],
    'sha plus extra argument' => ['desplegar '.str_repeat('a', 40).' now'],
    'semicolon' => ['ping; id'],
    'and list' => ['ping && id'],
    'pipe' => ['estado | cat'],
    'redirect' => ['estado > out'],
    'command substitution' => ['desplegar $(id)'],
    'backticks' => ['`id`'],
    'newline' => ["ping\nid"],
    'tab' => ["ping\tnow"],
    'double space' => ['desplegar  '.str_repeat('a', 40)],
]);

it('refuses a malformed sha', function (string $order) {
    $process = dispatcherRun($this->fx, $order);

    expect($process->getExitCode())->toBe(64)
        ->and($process->getErrorOutput())->toContain('order not allowed')
        ->and(dispatcherLog($this->fx))->toBe('');
})->with([
    'too short' => ['desplegar abc123'],
    'too long' => ['desplegar '.str_repeat('a', 41)],
    'not hex' => ['desplegar '.str_repeat('g', 40)],
    'uppercase hex' => ['desplegar '.str_repeat('A', 40)],
    'previsualizar' => ['previsualizar 123'],
]);

it('lists the pending migrations', function () {
    $process = dispatcherRun($this->fx, 'pendientes');

    expect($process->getExitCode())->toBe(0)
        ->and(dispatcherLog($this->fx))->toBe("artisan migrate:status --pending --no-ansi\n");
});

it('passes the exit code of puede-desplegar through', function (string $code) {
    $process = dispatcherRun($this->fx, 'puede-desplegar', ['STUB_PHP_EXIT' => $code]);

    expect($process->getExitCode())->toBe((int) $code)
        ->and(dispatcherLog($this->fx))->toBe("artisan sap:puede-desplegar --no-ansi\n");
})->with(['0', '1', '3']);

it('counts the migrations a commit would add without migrating', function () {
    dispatcherRepos($this->fx);
    $sha = dispatcherPush($this->fx['root'], [
        'database/migrations/2026_11_01_000009_create_jobs_table.php' => "<?php\n",
        'app/Modules/Sap/database/migrations/2026_11_02_000009_create_items_table.php' => "<?php\n",
        'database/migrations/0001_01_01_000000_create_users_table.php' => "<?php // changed\n",
        'app/Modules/Sap/Models/Item.php' => "<?php\n",
    ]);
    $before = dispatcherHead($this->fx);

    $process = dispatcherRun($this->fx, "previsualizar {$sha}");

    expect($process->getExitCode())->toBe(0)
        ->and($process->getOutput())->toContain("migrations: 2\n")
        ->and($process->getOutput())->toContain('create_items_table.php')
        ->and($process->getOutput())->not->toContain('create_users_table.php')
        ->and(dispatcherHead($this->fx))->toBe($before)
        ->and(dispatcherLog($this->fx))->toBe('');
});

it('deploys a fast-forward commit from origin/main', function () {
    dispatcherRepos($this->fx);
    $previous = dispatcherHead($this->fx);
    $sha = dispatcherPush($this->fx['root'], ['README.md' => "next\n"]);

    $process = dispatcherRun($this->fx, "desplegar {$sha}");

    expect($process->getExitCode())->toBe(0, $process->getErrorOutput())
        ->and($process->getOutput())->toContain("previous: {$previous}\n")
        ->and($process->getOutput())->toContain("deployed: {$sha}\n")
        ->and($process->getOutput())->toContain('revert')
        ->and(dispatcherHead($this->fx))->toBe($sha)
        ->and(dispatcherLog($this->fx))->toBe("artisan sap:puede-desplegar --no-ansi\ndeploy {$sha}\n")
        ->and(is_dir("{$this->fx['app']}/storage/despachar.lock"))->toBeFalse();
});

it('does nothing when the commit is already deployed', function () {
    dispatcherRepos($this->fx);
    $process = dispatcherRun($this->fx, 'desplegar '.dispatcherHead($this->fx));

    expect($process->getExitCode())->toBe(0)
        ->and($process->getOutput())->toContain('already deployed')
        ->and(dispatcherLog($this->fx))->toBe('');
});

it('refuses a commit that is not on origin/main', function () {
    dispatcherRepos($this->fx);
    $before = dispatcherHead($this->fx);
    $branch = dispatcherPush($this->fx['root'], ['README.md' => "branch\n"], 'feature');
    // The object exists in the app clone, so only the main check stops it.
    dispatcherGit($this->fx['root'], $this->fx['app'], 'fetch', '--quiet', 'origin', 'feature');

    foreach ([$branch, str_repeat('0', 40)] as $sha) {
        $process = dispatcherRun($this->fx, "desplegar {$sha}");

        expect($process->getExitCode())->toBe(65)
            ->and($process->getErrorOutput())->toContain('not on origin/main');
    }

    expect(dispatcherHead($this->fx))->toBe($before)
        ->and(dispatcherLog($this->fx))->toBe('')
        ->and(is_dir("{$this->fx['app']}/storage/despachar.lock"))->toBeFalse();
});

it('refuses a commit that is not a fast-forward of HEAD', function () {
    dispatcherRepos($this->fx);
    $older = dispatcherPush($this->fx['root'], ['README.md' => "older\n"]);
    $newer = dispatcherPush($this->fx['root'], ['README.md' => "newer\n"]);
    dispatcherGit($this->fx['root'], $this->fx['app'], 'pull', '--quiet', '--ff-only');

    $process = dispatcherRun($this->fx, "desplegar {$older}");

    expect($process->getExitCode())->toBe(65)
        ->and($process->getErrorOutput())->toContain('not a fast-forward')
        ->and(dispatcherHead($this->fx))->toBe($newer)
        ->and(dispatcherLog($this->fx))->toBe('');
});

it('refuses to deploy while another deploy holds the lock', function () {
    dispatcherRepos($this->fx);
    $before = dispatcherHead($this->fx);
    $sha = dispatcherPush($this->fx['root'], ['README.md' => "next\n"]);
    mkdir("{$this->fx['app']}/storage/despachar.lock");

    $process = dispatcherRun($this->fx, "desplegar {$sha}");

    expect($process->getExitCode())->toBe(75)
        ->and($process->getErrorOutput())->toContain('already running')
        ->and(dispatcherHead($this->fx))->toBe($before)
        ->and(dispatcherLog($this->fx))->toBe('')
        // The refused run must not release a lock it does not own.
        ->and(is_dir("{$this->fx['app']}/storage/despachar.lock"))->toBeTrue();
});

it('refuses to deploy when puede-desplegar says no', function () {
    dispatcherRepos($this->fx);
    $before = dispatcherHead($this->fx);
    $sha = dispatcherPush($this->fx['root'], ['README.md' => "next\n"]);

    $process = dispatcherRun($this->fx, "desplegar {$sha}", ['STUB_PHP_EXIT' => '1']);

    expect($process->getExitCode())->toBe(75)
        ->and($process->getErrorOutput())->toContain('puede-desplegar')
        ->and($process->getOutput())->not->toContain('previous:')
        ->and(dispatcherHead($this->fx))->toBe($before)
        ->and(dispatcherLog($this->fx))->toBe("artisan sap:puede-desplegar --no-ansi\n")
        ->and(is_dir("{$this->fx['app']}/storage/despachar.lock"))->toBeFalse();
});

it('fails when HEAD does not land on the commit after the deploy', function () {
    dispatcherRepos($this->fx);
    $before = dispatcherHead($this->fx);
    $sha = dispatcherPush($this->fx['root'], ['README.md' => "next\n"]);

    $process = dispatcherRun($this->fx, "desplegar {$sha}", ['DEPLOY_SCRIPT' => $this->fx['noop']]);

    expect($process->getExitCode())->toBe(70)
        ->and($process->getOutput())->not->toContain('deployed:')
        ->and($process->getErrorOutput())->toContain("expected {$sha}")
        ->and(dispatcherHead($this->fx))->toBe($before)
        ->and(is_dir("{$this->fx['app']}/storage/despachar.lock"))->toBeFalse();
});

it('reports HEAD, maintenance mode and today\'s errors without reading .env', function () {
    dispatcherRepos($this->fx);
    $date = new Process([$this->fx['bash'], '-c', 'date +%Y-%m-%d']);
    $today = trim($date->mustRun()->getOutput());
    $app = $this->fx['app'];

    file_put_contents("{$app}/.env", "APP_KEY=SENTINEL_ENV_VALUE_7f3a\nDB_PASSWORD=SENTINEL_ENV_VALUE_7f3a\n");
    touch("{$app}/storage/framework/down");

    $errors = [];
    foreach (range(1, 6) as $i) {
        $errors[] = "[{$today} 10:0{$i}:00] production.ERROR: failure {$i}";
    }
    $errors[] = "[{$today} 11:00:00] production.ERROR: ".str_repeat('x', 300);

    file_put_contents("{$app}/storage/logs/laravel.log", implode("\n", [
        '[2000-01-01 10:00:00] production.ERROR: an old failure',
        "[{$today} 09:00:00] production.WARNING: not an error",
        ...$errors,
        '#0 /home/app/vendor/stack/trace.php(12): a stack trace line',
    ])."\n");

    $process = dispatcherRun($this->fx, 'estado');
    $output = $process->getOutput();
    $lines = explode("\n", rtrim($output, "\n"));

    expect($process->getExitCode())->toBe(0)
        ->and($output)->toContain('head: '.dispatcherHead($this->fx))
        ->and($output)->toContain('maintenance: on')
        ->and($output)->toContain('errors today: 7')
        ->and($output)->not->toContain('failure 1')
        ->and($output)->not->toContain('failure 2')
        ->and($output)->toContain('failure 3')
        ->and($output)->not->toContain('old failure')
        ->and($output)->not->toContain('not an error')
        ->and($output.$process->getErrorOutput())->not->toContain('SENTINEL_ENV_VALUE_7f3a')
        ->and(count(array_filter($lines, fn (string $line) => str_contains($line, '.ERROR:'))))->toBe(5)
        ->and(max(array_map('strlen', $lines)))->toBeLessThanOrEqual(200)
        ->and(dispatcherLog($this->fx))->toBe('');
});

it('reports maintenance off and no errors on a quiet day', function () {
    dispatcherRepos($this->fx);
    $process = dispatcherRun($this->fx, 'estado');

    expect($process->getExitCode())->toBe(0)
        ->and($process->getOutput())->toContain('maintenance: off')
        ->and($process->getOutput())->toContain('errors today: 0');
});
