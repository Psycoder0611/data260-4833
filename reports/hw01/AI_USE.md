# AI Use

## 1. What did I use an AI assistant for, and what did I do myself?

I used an AI assistant mainly for guidance while working through the assignment, especially for understanding unfamiliar  LangChain, Ollama model concepts.

I created & tested the HTML form, JavaScript validation, Docker application, local Ollama setup, agent pipeline, non-determinism experiment & model-client conversation on my own machine. I also ran all of the experiments myself & used the actual O/P from my runs for the reported metrics.

## 2. One AI-produced output that was wrong or unsuitable

During the model-client experiment, the local Qwen3 model incorrectly mentioned a `/think` suffix while reviewing Python code even though I had not included `/think` in the code I submitted for review.

## 3. How did I detect or verify the problem?

I compared the model's review with the exact Python code I entered in the terminal. Since the input did not contain `/think`, I could confirm that this part of the model response was incorrect rather than an issue in my Python code.

I also verified my Python environment separately by checking the active interpreter and testing the LangChain imports directly from the terminal.

## 4. What did I change, and why does it work now?

I added `/no_think` to the instructions in `AGENT.md` and restarted the conversation so the previous incorrect response was not included in the new conversation history.

After the change, the model followed the required bullet-only review format more consistently. I also configured VS Code to use the same `.venv` Python interpreter that successfully ran the program from the terminal.