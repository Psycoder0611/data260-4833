## 1. What I used AI for and what I did myself
I used Claude and ChatGPT to understand the HW6 requirements and to plan the order of the work. I set up the branch and folders, ran Docker, MongoDB and Ollama on my own machine, tested the code, reviewed the results, ran every experiment, took every screenshot, and did all the Git work myself.

## 2. An AI suggestion that was unsuitable
The model call used qwen3:8b with its default settings. When I ran the chat endpoint for real, many replies came back empty. The code looked correct and passed the offline tests, which use a fake model, so the problem only showed up with the real model.

## 3. How I detected the problem
I noticed the empty replies while running the chat experiments. I then called the model directly with a short diagnostic. It used up its tokens (174) on hidden thinking and returned no visible text. The fake model in the offline tests never does this, which is why the tests did not catch it.

## 4. What I changed and why it works now
I turned off the hidden thinking for qwen3 (reasoning=False) in hw6/llm.py and added one retry with a larger token budget in case a reply is still empty. I also changed the fact extraction prompt so it keeps names. After this the replies were no longer empty, and I re-ran the tests and all experiments. Every number in the report comes from those real runs.
