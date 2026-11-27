<?php

use Tests\Modules\Sap\Support\RobotClient;

/*
| POST /api/robot/v1/version (docs/contrato-robot.md, section 13.1): the
| commit the server runs, read from the file deploy/deploy.sh writes after
| a good deploy, so the robot only updates itself to it.
*/

const VERSION_PATH = '/api/robot/v1/version';

const VERSION_SHA = '0123456789abcdef0123456789abcdef01234567';

beforeEach(function () {
    RobotClient::configure();
    $this->versionFile = tempnam(sys_get_temp_dir(), 'sap-commit-');
    config(['sap.deploy.commit_file' => $this->versionFile]);
});

afterEach(function () {
    if (is_file($this->versionFile)) {
        unlink($this->versionFile);
    }
});

it('answers the commit the last deploy wrote', function () {
    file_put_contents($this->versionFile, VERSION_SHA."\n");

    RobotClient::post($this, VERSION_PATH)->assertOk()->assertExactJson(['commit' => VERSION_SHA]);
});

it('answers the commit in lowercase when the file has it in uppercase', function () {
    file_put_contents($this->versionFile, '  '.strtoupper(VERSION_SHA)." \r\n");

    RobotClient::post($this, VERSION_PATH)->assertOk()->assertExactJson(['commit' => VERSION_SHA]);
});

it('answers null when no deploy wrote the file', function () {
    unlink($this->versionFile);

    RobotClient::post($this, VERSION_PATH)->assertOk()->assertExactJson(['commit' => null]);
});

it('answers null when the file does not hold one full commit', function (string $content) {
    file_put_contents($this->versionFile, $content);

    RobotClient::post($this, VERSION_PATH)->assertOk()->assertExactJson(['commit' => null]);
})->with([
    'empty' => [''],
    'blank' => ["  \n"],
    'short' => [substr(VERSION_SHA, 0, 39)],
    'long' => [VERSION_SHA.'8'],
    'not hex' => [substr(VERSION_SHA, 0, 39).'g'],
    'two lines' => [VERSION_SHA."\n".VERSION_SHA],
    'a branch name' => ['refs/heads/main'],
    'padded past 256 bytes' => [VERSION_SHA.str_repeat(' ', 217)],
]);

it('refuses an unsigned request with the usual 401', function () {
    file_put_contents($this->versionFile, VERSION_SHA);

    RobotClient::post($this, VERSION_PATH, headers: ['X-Robot-Signature' => null])
        ->assertUnauthorized()
        ->assertExactJson(['message' => 'Firma inválida.']);
});

it('refuses a query string as every robot route does', function () {
    RobotClient::post($this, VERSION_PATH, query: 'commit=1')
        ->assertStatus(400)
        ->assertExactJson(['message' => 'Las rutas del robot no llevan query string.']);
});
