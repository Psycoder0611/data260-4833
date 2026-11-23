# AI_USE - HW11 (Trapti Kulshrestha, SID4 4833)

## 1. What I used an AI assistant for, and what I did myself

I used ChatGpt and Claude to help me understand this homework & how Muse (Meta's agent) works or function. I read the policy, code, decoding part, the fixtures and the labels, and committed them before the first run on Muse. Claude helped me in drafting my policy.md, the fixture files, the golden labels and the watch.py changes; I read them and committed them before the first run on Muse.

I set up Muse, ran every command and test in it myself, and took every screenshot. The decisions, metrics, latency and usage in the report all come from my own Muse runs. I did not use any AI to decide the answers in Part 7. They are based on what my runs showed and I checked each claim against my screenshots.

## 2. One AI output that was wrong

On my first run on the real sources, Muse reported "0 new, 0 duplicates suppressed, 0 alerts, 0 digest, 0 need review", which reads as a quiet day. Its own task list also called the check "no source errors found". That was wrong, because all four live sources had failed.

Muse made a second mistake later. When I asked it to send the Calder Foods -6.0% alert again, it posted the whole HIGH alert a second time, although the policy says an alert is posted only after decide allows it.

## 3. How I detected it

The live run took 97 seconds and found nothing, which seemed too long for an empty result. I asked Muse to run the trace for that run and to list any source_error steps with the exact message. It answered with four, which contradicted both its summary and its own task label.

For the repeated alert, I did not trust the chat message. I asked Muse to trace that item and to say whether it had called decide again. The trace showed only the original decision and effect, and Muse said it had only repeated the alert at my request.

## 4. What changed

With Claude's suggestion I changed watch.py so the pending output lists failed sources, their errors and a warning that 0 candidates is not an all-clear. I uploaded the new file to Muse and checked the checksum. I also added a release requirement for a deliberately broken source. The policy, fixtures and golden labels did not change. watch.py changed after the labels were committed, so I name that here. The next morning's scheduled run on Muse's live sources named the failed EDGAR source in its summary, so the warning works.

I did not fix the repeated alert. The database stayed correct (still 5 notifications), but my duplicate metric did not see the second message. I listed the fix as a release requirement in Part 7: a request for an alert that was already sent must be answered from the ledger and not by reposting it.
