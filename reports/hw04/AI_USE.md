6.1 What I used AI for vs. what I did myself
I used ChatGPT and Claude mainly as learning and support tools while completing this homework. I used them to understand concepts such as React props and hooks, server-side sessions, the N+1 query problem, eager loading, FAISS retrieval, RAG configurations, and context engineering. I also used AI to clarify assignment requirements, review code, explain errors, and suggest possible debugging steps.
I completed the actual implementation in my own repository, created and modified the project files, configured MySQL, ran the FastAPI and React applications, tested the APIs in Postman, created the database tables and seed data, ran all benchmark and RAG experiments, collected screenshots, verified the outputs, and prepared the final report. I also checked the AI suggestions against the actual program behavior before keeping them in my submission.

6.2 One AI-produced output that was wrong or unsuitable
One issue occurred while adding the fixed N+1 endpoint. The initial code placement caused the /fixed route to be declared after the dynamic /{trial_id} route. When I tested /api/hw4/trials/fixed, FastAPI interpreted the word fixed as the value of trial_id and returned a 422 validation error.

6.3 How I detected or verified the problem
I detected the issue during my own Postman testing. The response showed that FastAPI was trying to parse "fixed" as an integer path parameter for trial_id. I checked the router code and compared the route declaration order. This confirmed that the static /fixed path was being matched incorrectly because of where it was placed in the file.

6.4 What I changed and why the corrected version works
I moved the /fixed endpoint above the /{trial_id} endpoint in routers/hw4_trials.py. After this change, FastAPI matched /fixed as a static route before evaluating the dynamic ID route. I tested the endpoint again in Postman for page sizes 10, 50, and 200, and all requests returned 200 OK. I also included the endpoint in the final smoke test, where both the naive and fixed routes passed successfully.