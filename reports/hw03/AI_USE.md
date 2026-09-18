# AI Use

## 1. What did I use an AI assistant for, and what did I do myself?

I used chatgpt and Claude mainly for guidance while extending my existing FastAPI project, understanding the authentication/session requirements of LlamaIndex retrieval pipeline & debugging errors as they appeared.

I personally selected the three ClinicalTrials.gov studies, created the local corpus, ran all commands and experiments, tested the login/logout/session behavior, captured the screenshots, reviewed the retrieval outputs & verified the generated files and metrics in my local environment.

## 2. What was one AI-produced suggestion that was unsuitable, or one result that I independently verified?

I independently verified the suggested FastAPI & retrieval code instead of assuming it would work directly. During the authentication setup, the provided starter code used a TemplateResponse calling style that was not compatible with my installed Starlette version. I also verified every retrieval technique by checking the actual terminal output and saved CSV files.

## 3. How did I detect the problem or verify the result?

I detected the TemplateResponse problem because the application returned a 500 error with `TypeError: unhashable type: 'dict'`. I used the traceback to identify the failing call in `routers/auth.py`.

For the retrieval work, I verified the results by printing the embedding dimensions, vector shapes, retrieved source files, store scores, cosine similarities, chunk lengths, previews, and retrieval latency. I also compared the retrieved sources against the expected sources recorded earlier in `questions.yaml`.

## 4. What did I change, and why does it work now?

I updated the TemplateResponse calls to use explicit `request`, `name`, and `context` arguments, which matched the installed Starlette API and allowed the templates to render correctly.

For retrieval evaluation, I kept the five questions fixed before running the experiments, saved machine-readable outputs for all three techniques, and added explicit cosine-similarity and latency calculations. This made the comparison reproducible and allowed the final metrics to be computed directly from the saved raw results rather than manually.