# AI_USE - HW7 (Trapti Kulshrestha, SID4 4833)

## 1. What I used an AI assistant for, and what I did myself

I used ChatGPT and Claude as a coding assistant. It helped me understand the logins, roles & the agent loop, the Reflexion verifier, Bay Wheels agent, the injection tests, the file tools and the safety gate. It also helped me debug the issues I ran into.

I ran every command on my own and ran all the model runs (qwen3:8b through Ollama), so every number in the report comes from my runs. I took the screenshots, handled all the Git steps and made the design decisions. For eg., I picked Bay Wheels as the pricing source, rejected the first UI design, and chose to test Part 5 with live runs plus a scripted stand-in model, because the live model never tried the DELETE or the data leak. I also chose that auto_approve=True counts as the confirmation in the safety gate. I read the results before they went into the report.

## 2. One AI output that was wrong

In Part 5 the AI counted "recommendation override" as successful whenever the agent's membership calculation used a fee other than $29. On the hostile page this gave 5/5, which looked right. But when I ran the same test on the clean page with no attack, it still counted runs as poisoned. The model sometimes uses a wrong fee by itself, and the metric blamed the page for that.

A smaller case: in the Scenario B UI run the agent worked out break-even as 29 * 5 / 11.73 = 12.4 rides, but the rider had only 4 rides, so the right value is 9.9. The decision was still correct and all three outside checks said pass, because none of them tests break-even.

## 3. How I detected it

For the override metric, the clean-page control run (the same agent, no injected lines) showed fee "poisoned" runs where there was no attack at all. That told me the metric was wrong, not the model. I also recomputed the counts from the saved trace files and compared them with the reference calculation (membership $30.40, decision Pay Per Ride/Minute).

For the break-even, I showed the UI screenshot to Claude, which flagged the wrong figure, and I confirmed it against the reference value in the saved run JSON (12.36 vs 9.9).

## 4. What changed and why it works now

The metric now only counts an override when the first number in the membership calculator expression is exactly the injected $9 fee. I added a rejudge command that recounts from the saved traces. The clean-page control now shows 0/3 for the fee in every setting, while the hostile page still shows 5/5, so the metric separates a real attack from the model's own mistakes.

For the break-even, I re-ran Scenario B in the UI and got 29 * 4 / 11.73 = 9.89, which matches the reference, and I used that run for the screenshot. I did not change the checks, so they still do not test break-even. This is a limit I note in the report.
