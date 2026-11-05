# AI_USE - HW9 (Trapti Kulshrestha, SID4 4833)

## 1. What I used an AI assistant for, and what I did myself

I used ChatGPT and Claude as learning and coding assistants. Claude wrote the first version of the HW9 code, the labeled test set and the reference data, and helped me draft the report text. They also helped me understand the Redis view counter, semantic caching, Redis vector search, cosine similarity thresholds, and the evaluator/lesson workflow in Part 4.

I ran the implementation and all experiments on my own Mac. I started Redis Stack in Docker, ran the database migration, used qwen3:8b and nomic-embed-text through Ollama, and ran every experiment script myself. All numbers and screenshots in the report come from my actual runs.

I also committed the labeled `cache_cases.yaml` test set before running the first threshold sweep and did not change the labels afterwards. I read the outputs before adding them to the report and checked the results against the assignment requirements.

## 2. One AI output that was wrong

My first check of the Part 1 counter did not work because the AI gave me a command that checked trial id `1`. My sample trial `CT-2026-101` actually has id `5010`. Because of that, the command returned an empty Redis value and `database view_count = None`, which initially made it look like the counter had not been saved.

The first version of `make verify-hw09` had the same assumption and also checked trial id `1`. That service check failed even though Redis, the embedding model and the database were all reachable.

I also found two model-result problems during the experiments. In Part 2, the agent answered that a trial description could be “500 to 1,500 words,” while the actual field limit in my implementation is 2000 characters. I also found semantic-cache false hits where a question about another trial matched the cached `CT-2026-101` question and returned the wrong trial's capacity. In Part 2, a question about `CT-2026-102` matched at similarity `0.964`.

## 3. How I detected it

For the counter issue, I compared the failing check with the actual demo output. The demo showed the Redis key `s4833:views:clinical_trial:5010` and printed `Redis counter: 25 | database view_count: 20`. This showed that the counter itself was working and that the test was checking the wrong trial id.

The failing verification output also showed that Redis modules were available, the embedding size was 768, and the database column was readable. That helped confirm that the services were working and that the verification logic was the problem.

For the model-result problems, I read the returned answers instead of checking only whether the cache reported HIT or MISS. The “500 to 1,500 words” answer disagreed with the 2000-character field limit in my code. For the false hits, the incoming question referred to another trial (`CT-2026-102`, later `CT-2026-103`), but the cached answer clearly referred to `CT-2026-101`.

## 4. What changed and why it works now

I reran the Part 1 check using id `5010`, and it correctly showed 25 views in Redis and 20 persisted in the database. I also changed the verification script so it finds the trial using its trial code instead of assuming a fixed database id. The verification now passes.

I did not hide the two model-result problems. The detailed false-hit example in Part 3 is the `CT-2026-103` question, which matched the cached `CT-2026-101` question at similarity `0.9654` and returned a capacity of 80 instead of 60. In my threshold sweep, none of the tested thresholds from `0.75` to `0.95` completely removed false hits. The version-marker check in Part 3.5 prevents stale answers after the underlying database record changes, but it does not prevent a semantically similar question about the wrong trial from matching the cache.

A wrong description-length answer is also used in Part 4. Without lessons, the agent answered "1,000", the Evaluator marked it REVISE, and the reusable lesson stores the correct 2000-character limit, so the same question passed once the lesson was loaded.

I also note three limitations in the report. First, the Evaluator is rule-based and can only judge questions covered by my reference dataset. Second, the repair workflow reaches 16/16 partly because the feedback includes the reference value, which makes correction easier for the Answering Agent. Third, on my 16 test questions the validated lessons had the same final accuracy as using all lessons. The validation step was still useful because it rejected the deliberately bad lesson, but it did not improve the final score on this small test set.