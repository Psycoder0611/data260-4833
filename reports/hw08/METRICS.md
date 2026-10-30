# HW8 metrics (SID4 4833, seed 4833, verify seed 264833)


## JMeter: Kafka endpoint vs direct endpoint (100 threads, 10 s ramp-up, 1 loop)

| Endpoint | Samples | Avg (ms) | Min (ms) | Max (ms) | p90 (ms) | p95 (ms) | Error % | Throughput (req/s) |
|---|---|---|---|---|---|---|---|---|
| Kafka (request/response) | 100 | 9.0 | 4.0 | 13.0 | 11.0 | 11.0 | 0.0% | 10.09 |
| Direct (no Kafka) | 100 | 3.0 | 2.0 | 10.0 | 4.0 | 5.0 | 0.0% | 10.1 |

## Part 3 failure table (before vs after)

| Failure | Before (fix off) | Before: evidence | After (fix on) | After: evidence |
|---|---|---|---|---|
| Duplicate delivery | idempotency off | 2 drafts for 1 request | idempotency on | 1 draft, 1 duplicate skipped |
| Consumer dies mid-work | commit on receive | redelivered=False, draft produced=False | commit after success | redelivered=True, draft produced=True |
| Poison message | unbounded retry, no DLQ | 14 attempts seen, next message processed=False | max 3 attempts + dead letter | 3 attempts, 1 in dead letter, next message processed=True |

## Ordering (20 VERIFY_SEED messages, 2 partitions, 2 Writers in one group)

| Run | Processed | Order inversions | Entities out of order | Entities split over partitions |
|---|---|---|---|---|
| No key | 20 | 2 | 2 | 4 |
| Key = entity | 20 | 0 | 0 | 0 |
