## Model Client and Token Accounting

I created a reusable model adapter in `src/model_client.py` and used it from
`hw1_client.py`. The system instructions were loaded from `AGENT.md`, which
asked the model to respond using only bullet points for code reviews.

I ran a five-turn conversation and checked `/stats` after turn 3 and turn 5.
The model followed the bullet-only response format, and token usage was printed
after each model response.

### Why is prior conversation context resent with every turn?

The model does not automatically remember previous messages between separate
requests. To continue a conversation, the earlier system, user, and assistant
messages are sent again with the new message so the model has the context it
needs to respond consistently.

### How is a system prompt different from a user message?

A system prompt gives the model overall instructions about how it should
behave during the conversation. A user message contains the actual request
from the user. In this experiment, `AGENT.md` acted as the system prompt and
required the model to give bullet-only code reviews.

### Why do input tokens grow over a conversation?

Input tokens increase because each new model request includes the previous
conversation history along with the latest user message. As the conversation
gets longer, more text has to be sent back to the model.

### What eventually limits that growth?

The model has a limited context window, so there is a maximum amount of text
that can be included in one request. Once the conversation becomes too large,
older content must be removed, summarized, or otherwise reduced to stay within
that context limit.