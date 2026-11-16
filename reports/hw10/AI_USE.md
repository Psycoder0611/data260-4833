# AI_USE - HW10 (Trapti Kulshrestha, SID4 4833)

## 1. What I used an AI assistant for, and what I did myself

I used ChatGpt and Claude as a teaching assistant to understand the HW concepts. It also helped me understand DeepEval's GEval metric, Spearman correlation as a measure of agreement & how to read p50 and p95 latency.

I ran everything myself on my own Mac: Kafka and Redis in Docker, the three agents in three terminals, qwen3:8b and nomic-embed-text through Ollama, the Streamlit dashboard, and every experiment script. All numbers and screenshots in this report come from my own runs.

I gave the 20 human labels myself, by reading each Writer draft and applying a short 1-to-5 guide.I also committed eval_cases.json and human_labels.csv before I ran the judge on them, and I did not change a label afterwards. I also read each output before putting it in the report and compared the results with the assignment requirements.

## 2. One AI output that was wrong

The first version of the judge gave scores that did not match its own written reasons. In my first Part 2 run, the judge wrote that the Writer's draft "correctly addresses the question by providing the participant capacity and sponsor details ... without inventing any additional facts or details", and then gave it a score of 3 out of 5. Another draft whose reason said it "correctly identifies the category ... accurately without inventing any additional details" also got a 3. The reasons were positive but the scores were low.

The assistant also made other mistakes that I caught along the way. The semantic cache from HW9 treated different trial-code questions as near-duplicates (similarity above 0.85), so my fresh test questions were answered by the cache instead of the pipeline. A preflight check crashed with an aiokafka traceback. A first version of the dashboard drew the "where a cache miss spends its time" chart with an axis that started at 8.5 percent instead of 0, which hid the smallest stages and made Evaluation look cut off, and the first latency chart pushed the cache-hit points off the screen. The new latency tiles also crashed on a time window with no cache hits, which made one offline test fail in `make verify-hw10`.

## 3. How I detected it

I did not accept the first judge scores. I read the judge's reason next to each score, and a reason that praised an answer did not fit a 3 out of 5. Looking at the prompt that DeepEval builds, I saw that my rubric text labelled its bands "Score 1" to "Score 5", while GEval itself works on a 0 to 10 scale, so the judge was mixing the two scales.

For the other problems, I noticed the cache issue because a question about a new trial printed "already in the cache" on a fresh run. I noticed the chart problems by looking at the real screenshots from my own dashboard instead of trusting that the code was right, and `make verify-hw10` reported the failing offline test.

## 4. What changed and why it works now

I replaced the "Score N" labels in the rubric with plain descriptions of each band, added an explicit step that tells the judge to answer with a whole number from 0 to 10, and now store the judge's raw 0-to-10 score next to the mapped 1-to-5 score so a mismatch is visible. I threw the first run away (it is kept in a folder that is not committed), deleted its cache entries and ran Part 2 again. In the second run the scores follow the reasons.

For the cache problem I gave HW10 its own cache namespace (s4833:hw10:semcache: with its own index) so that HW9 entries cannot answer HW10 questions. The preflight no longer checks consumer-group details through the admin API. I fixed the chart axes, switched the latency chart to a log scale so hits and misses both show, and made the new tiles show "n/a" when a window has no hits.

I want to be clear about what the fix did not do. The judge is no longer self-contradictory, but Part 3 shows it is still more generous than I am on borderline drafts and it disagrees with me about one off-topic request, so the fix did not make it a trustworthy gate. I describe that in Part 3.
