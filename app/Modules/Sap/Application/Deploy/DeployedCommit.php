<?php

namespace App\Modules\Sap\Application\Deploy;

/**
 * The commit the server runs (docs/contrato-robot.md, section 13.1), read
 * from the file deploy/deploy.sh writes after a good deploy. Never runs git
 * or any other process: a missing, empty or malformed file means unknown.
 */
final class DeployedCommit
{
    private const MAX_BYTES = 256;

    /**
     * The 40-character sha in lowercase, or null when the file does not
     * hold exactly one (surrounding whitespace aside).
     */
    public function current(): ?string
    {
        $file = (string) config('sap.deploy.commit_file');

        if ($file === '' || ! is_file($file) || ! is_readable($file)) {
            return null;
        }

        // A sha is 41 bytes with its newline; anything far longer is not one.
        $content = @file_get_contents($file, length: self::MAX_BYTES + 1);

        if ($content === false || strlen($content) > self::MAX_BYTES) {
            return null;
        }

        $sha = strtolower(trim($content));

        return preg_match('/^[0-9a-f]{40}$/', $sha) === 1 ? $sha : null;
    }
}
