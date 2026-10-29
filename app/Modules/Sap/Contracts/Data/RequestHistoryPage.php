<?php

namespace App\Modules\Sap\Contracts\Data;

/**
 * One page of the request history; total counts every request that
 * matches the filters.
 */
final readonly class RequestHistoryPage
{
    /**
     * @param  list<RequestHistoryItem>  $items
     */
    public function __construct(
        public array $items,
        public int $total,
        public int $page,
        public int $perPage,
    ) {}
}
