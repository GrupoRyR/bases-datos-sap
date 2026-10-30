<?php

namespace App\Modules\Sap\Contracts\Data;

/**
 * An update request with everyone who asked for it, in the order they joined.
 */
final readonly class RequestHistoryItem
{
    /**
     * @param  list<RequesterData>  $requesters
     */
    public function __construct(
        public UpdateRequestData $request,
        public array $requesters,
    ) {}
}
