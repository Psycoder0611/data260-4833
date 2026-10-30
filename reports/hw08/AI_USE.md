# AI_USE - HW8 (Trapti Kulshrestha, SID4 4833)

## 1. What I used an AI assistant for, and what I did myself

I used Claude and ChatGpt as a learning tool which helped me understand the assignment & the process of Kafka worker, the FastAPI wrapper, JMeter plans.

I started Kafka with Docker, ran every command on my own Mac, ran the model (qwen3:8b through Ollama) and ran JMeter myself, so every number in the report comes from my runs. I took all the screenshots and made the report. I read each log and result before it went into the report. For example, I reran the ordering test when the first run came out in order by luck, and I cleared JMeter and ran it again when the sample count was wrong.

## 2. One AI output that was wrong

In Part 3 the poison-message test printed a summary line that said 14 failed attempts. But when I counted the FAILED lines in the Writer log from the same run, there were 18. The summary looked fine on its own, and the "after the fix" case (3 attempts, then the dead-letter topic) was correct, so the mismatch was easy to miss. The summary was wrong because the test counted the attempts while the Writer was still retrying in the background.

A smaller case: my first unkeyed ordering run came out completely in order, with zero inversions. That looked like the order problem did not exist, but it only meant the two Writers happened to be fast enough that run. A third case was in JMeter, where the Summary Report showed 200 and then 300 samples for a plan with 100 threads and loop count 1.

## 3. How I detected it

For the poison test I compared the summary line with the real Writer log of the same run. The numbers did not match (14 against 18), so I knew the test, and not Kafka, was wrong.

For ordering, I did not trust a result that showed nothing, so I ran the test again. The second run split four entities across both partitions and gave two inversions (CT-2026-107 as 3, 1, 2, 4 and CT-2026-109 as 1, 2, 4, 3).

For JMeter, 100 threads with one loop must give exactly 100 samples, so 200 and 300 told me the old results were still in the listeners.

## 4. What changed and why it works now

The poison test now stops the Writer first and only then counts the attempts, so the summary and the log agree. After the fix my rerun showed 14 in both places. I reran the ordering test, and the report text describes the result that actually happened. The unkeyed result changes from run to run (I saw between 2 and 5 inversions), but the keyed run was always 0 inversions, because the entity id as the key keeps one entity in one partition. In JMeter I press Clear All before every run. Both plans now show exactly 100 samples with 0.00% errors.

I note two limits in the report. The failure tests use a stub Writer so that they are fast and repeatable, and the unkeyed ordering numbers depend on timing, so I report them as examples and not as fixed values.
