# HW2 AI Use

## 1. What did I use an AI assistant for, and what did I do myself?

I used Claude and ChatGPT to help me understand the required tools & terminologies, review code structure, explain LangGraph concepts, FastAPI, troubleshoot errors.

I personally created, wrote and modified the files in my repository, ran the commands locally, installed the required packages, tested the FastAPI application, ran the LangGraph workflow, executed all schema/ceiling/adversarial experiments, inspected the outputs & saved the measured results.

## 2. What was one AI-produced output that was wrong or unsuitable, or one thing I independently verified?

One unsuitable suggestion was the initial adversarial experiment design using a Planner-attempt ceiling of 2. On my local qwen3:8b model, the second Planner retry repeatedly stalled for a long time instead of terminating quickly.

I also independently verified that the Pydantic validator correctly rejected invalid short tags such as `AI`, `ML`, and `X`.

## 3. How did I detect the problem or verify the result?

I detected the adversarial-run problem by observing the terminal. The graph reached:

`Planner attempt: 2`

and then remained there for more than 1 hour without producing another graph event.

I verified the validation behavior from the terminal output showing:

`PYDANTIC: Validation failed`

with the message that each tag must contain between 3 and 30 characters.

I also checked the generated CSV and JSON experiment files under `reports/hw02/raw/` instead of relying only on console text.

## 4. What did I change, and why does it work now?

I shortened the Pydantic feedback sent back to the Planner so it only includes the useful validation message instead of the full error dump.

For the bounded adversarial experiment, I used a Planner-attempt ceiling of 1. This allows the graph to generate one adversarial proposal, validate it, observe the failure, and terminate at the configured safety ceiling without starting the second local-model request that was repeatedly hanging.

The final adversarial experiment completed all five runs & reached the configured ceiling in 5/5 runs.








