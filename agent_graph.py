import json

from src.model_client import ModelClient
from typing import TypedDict, Dict, Any
from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel, Field, ValidationError, field_validator


# I am defining the shared state that moves through my LangGraph.
# Every node can read values from this state and return updates to it.
class AgentState(TypedDict):

    # Original input fields
    title: str
    content: str
    email: str
    strict: bool
    task: str

    # I am storing my reusable model client here
    # so Planner and Reviewer do not create ChatOllama directly.
    llm: Any

    # Planner output
    planner_proposal: Dict[str, Any]

    # Reviewer output
    reviewer_feedback: Dict[str, Any]

    # I am using this to prevent an infinite correction loop.
    turn_count: int

    # I will use this later for the maximum allowed graph turns.
    turn_ceiling: int

    # I am counting Planner attempts separately so I can
    # classify first-attempt and retry outcomes in my experiments.
    planner_attempts: int

# ---------------------------------------------------------
# Planner output schema
# ---------------------------------------------------------

class PlannerOutput(BaseModel):
    """
    I am using Pydantic to validate the Planner output
    before the graph accepts it.
    """

    # I require exactly 3 tags.
    # Each tag must contain between 3 and 30 characters.
    tags: list[
        str
    ] = Field(
        min_length=3,
        max_length=3
    )

    summary: str


    # I am checking the length of every individual tag.
    @field_validator("tags")
    @classmethod
    def validate_tags(cls, tags):

        for tag in tags:

            if len(tag) < 3 or len(tag) > 30:

                raise ValueError(
                    "Each tag must contain between 3 and 30 characters."
                )

        return tags


    # HW2 requires the summary to contain no more than 25 words.
    @field_validator("summary")
    @classmethod
    def validate_summary(cls, summary):

        word_count = len(
            summary.split()
        )

        if word_count > 25:

            raise ValueError(
                "Summary must contain no more than 25 words."
            )

        return summary


def planner_node(state: AgentState) -> Dict[str, Any]:
    """
    I am using the Planner node to generate
    exactly 3 topical tags and a short summary.
    """

    print("--- NODE: Planner ---")

    planner_attempts = state.get(
        "planner_attempts",
        0
    ) + 1

    print(
        f"Planner attempt: {planner_attempts}"
    )

    # I am reading the reusable model client from the shared graph state.
    llm: ModelClient = state["llm"]

    # If the Reviewer found problems earlier,
    # I am including that feedback in the next Planner attempt.
    reviewer_feedback = state.get(
        "reviewer_feedback",
        {}
    )

    feedback_text = ""

    if reviewer_feedback:
        feedback_text = (
            "\n\nThe previous attempt was rejected. "
            "Fix every problem described below and return a corrected result.\n"
            "Reviewer / validation feedback:\n"
            + json.dumps(
                reviewer_feedback,
                indent=2
            )
        )


    # I am clearly telling the model what JSON structure I expect.
    messages = [
        {
            "role": "system",
            "content": (
                "You are the Planner. "
                "Return ONLY valid JSON with no markdown or code fences. "
                "The JSON must contain exactly two keys: "
                "'tags' and 'summary'. "
                "'tags' must be an array of exactly 3 topical strings. "
                "Each tag should be between 3 and 30 characters. "
                "'summary' must contain no more than 25 words."
            )
        },
        {
            "role": "user",
            "content": (
                f"Task: {state['task']}\n\n"
                f"Title: {state['title']}\n"
                f"Content: {state['content']}\n"
                f"Strict mode: {state['strict']}"
                f"{feedback_text}"
            )
        }
    ]


    # All model calls are going through ModelClient.
    response = llm.complete(messages)


    raw_content = response["content"]


    # I am trying to parse the model response as JSON.
    # I am not fixing invalid output here because HW2 requires
    # schema validation and retry behavior later.
    try:

        proposal = json.loads(
            raw_content
        )

    except json.JSONDecodeError:

        proposal = {
            "raw_output": raw_content,
            "parse_error": (
                "Planner response was not valid JSON."
            )
        }


    return {
    "planner_proposal": proposal,

    # This is a new proposal, so the previous review
    # should not remain active.
    "reviewer_feedback": {},

    "planner_attempts": planner_attempts
}


def reviewer_node(state: AgentState) -> Dict[str, Any]:
    """
    I am using the Reviewer node to first validate
    the Planner output with Pydantic and then review its quality.
    """

    print("--- NODE: Reviewer ---")

    llm: ModelClient = state["llm"]

    planner_proposal = state.get(
        "planner_proposal",
        {}
    )


    # -----------------------------------------------------
    # Step 1: Pydantic schema validation
    # -----------------------------------------------------

    try:

        validated_output = PlannerOutput.model_validate(
            planner_proposal
        )

        print(
            "--- PYDANTIC: Planner output is valid ---"
        )


    except ValidationError as error:

        # I am storing the real Pydantic validation error
        # so the Planner can use it during the next retry.
        # I am keeping the validation feedback concise so the
    # Planner receives the actual problem without a very long error dump.
        validation_message = "; ".join(
            item["msg"]
            for item in error.errors()
        )

        print(
            "--- PYDANTIC: Validation failed ---"
        )

        print(validation_message)

        return {
            "reviewer_feedback": {
                "issues": [
                    validation_message
                ],
                "approved": False,
                "validation_failed": True
            }
        }


    # -----------------------------------------------------
    # Step 2: Reviewer quality check
    # -----------------------------------------------------

    # Pydantic confirms the required structure.
    # I am now asking the Reviewer to check whether
    # the tags and summary are actually relevant.

    messages = [
        {
            "role": "system",
            "content": (
                "You are the Reviewer. "
                "The Planner output has already passed structural "
                "Pydantic validation. "
                "Now review the quality and relevance of the result. "
                "Return ONLY valid JSON with no markdown or code fences. "
                "Use exactly these keys: 'issues' and 'approved'. "
                "'issues' must be an array of strings. "
                "'approved' must be true only when there are no issues. "
                "Check that the tags are topical and useful, "
                "and that the summary accurately represents the input."
            )
        },
        {
            "role": "user",
            "content": (
                "Original title:\n"
                f"{state['title']}\n\n"

                "Original content:\n"
                f"{state['content']}\n\n"

                "Planner proposal:\n"
                + json.dumps(
                    validated_output.model_dump(),
                    indent=2
                )
            )
        }
    ]


    response = llm.complete(
        messages
    )

    raw_content = response["content"]


    try:

        feedback = json.loads(
            raw_content
        )

    except json.JSONDecodeError:

        feedback = {
            "issues": [
                "Reviewer response was not valid JSON."
            ],
            "approved": False
        }


    return {
        "reviewer_feedback": feedback
    }


def supervisor_node(state: AgentState) -> Dict[str, Any]:
    """
    I am using the Supervisor node to update
    the shared state before deciding where to go next.
    """

    print("--- NODE: Supervisor ---")

    # I am increasing the turn counter each time
    # the Supervisor is reached.
    current_turn = state.get(
        "turn_count",
        0
    )

    new_turn = current_turn + 1

    print(
        f"Turn count: {new_turn}"
    )

    return {
        "turn_count": new_turn
    }


def router_logic(state: AgentState):
    """
    I am using this routing function to decide
    which node should run next.
    """

    turn_count = state.get(
        "turn_count",
        0
    )

    turn_ceiling = state.get(
        "turn_ceiling",
        10
    )

    planner_proposal = state.get(
        "planner_proposal",
        {}
    )

    reviewer_feedback = state.get(
        "reviewer_feedback",
        {}
    )



    # If there is no Planner proposal yet,
    # the Planner needs to run first.
    if not planner_proposal:

        print(
            "--- ROUTER: No proposal -> Planner ---"
        )

        return "planner"


    # If the Planner has produced something but
    # the Reviewer has not checked it yet,
    # I am routing to the Reviewer.
    if not reviewer_feedback:

        print(
            "--- ROUTER: Proposal exists -> Reviewer ---"
        )

        return "reviewer"


    # I am reading whether the Reviewer approved
    # the current Planner proposal.
    approved = reviewer_feedback.get(
        "approved",
        False
    )

    issues = reviewer_feedback.get(
        "issues",
        []
    )


    # If the Reviewer approves the proposal and
    # reports no issues, the graph can finish.
    if approved and not issues:

        print(
            "--- ROUTER: Approved -> END ---"
        )

        return END


    # I am checking the ceiling only when another Planner retry
    # would be needed. # If another correction is required, I check whether
    # the maximum number of Planner attempts has been reached.

    planner_attempts = state.get(
        "planner_attempts",
        0
    )

    if planner_attempts >= turn_ceiling:

        print(
            "--- ROUTER: Planner attempt ceiling reached -> END ---"
        )

        return END


    # If the Reviewer found problems,
    # I am sending the task back to the Planner
    # so it can correct the proposal.
    print(
        "--- ROUTER: Issues found -> Planner ---"
    )

    return "planner"


def build_graph():
    """
    I am assembling my Planner, Reviewer and Supervisor
    nodes into one stateful LangGraph workflow.
    """

    # I am creating a graph that uses AgentState
    # as the shared memory between all nodes.
    workflow = StateGraph(AgentState)

    # I am registering each Python function as a graph node.
    workflow.add_node(
        "supervisor",
        supervisor_node
    )

    workflow.add_node(
        "planner",
        planner_node
    )

    workflow.add_node(
        "reviewer",
        reviewer_node
    )


    # The Supervisor is the first node that runs.
    workflow.add_edge(
        START,
        "supervisor"
    )


    # The Supervisor uses router_logic() to decide
    # whether the next step is Planner, Reviewer or END.
    workflow.add_conditional_edges(
        "supervisor",
        router_logic,
        {
            "planner": "planner",
            "reviewer": "reviewer",
            END: END
        }
    )


    # After the Planner finishes, I return control
    # to the Supervisor so it can decide what happens next.
    workflow.add_edge(
        "planner",
        "supervisor"
    )


    # After the Reviewer finishes, I also return control
    # to the Supervisor.
    workflow.add_edge(
        "reviewer",
        "supervisor"
    )


    # I am compiling the graph so it can be executed.
    return workflow.compile()


def main():
    """
    I am running one example through the graph
    and printing the state returned by each node.
    """

    # I am creating the same reusable ModelClient
    # that I used in HW1.
    llm = ModelClient(
        model="qwen3:8b",
        temperature=0.0
    )


    # I am building the LangGraph workflow.
    graph = build_graph()


    # This is the initial shared state.
    initial_state: AgentState = {

        "title":
            "AI-Assisted Sepsis Detection",

        "content":
            (
                "Machine learning models can analyze patient "
                "vital signs and laboratory measurements to help "
                "identify patients who may be at risk of sepsis."
            ),

        "email":
            "student@sjsu.edu",

        "strict":
            True,

        "task":
            (
                "Generate exactly three topical tags and "
                "a summary of no more than 25 words."
            ),

        "llm":
            llm,

        # No proposal exists when the graph starts.
        "planner_proposal":
            {},

        # No review exists when the graph starts.
        "reviewer_feedback":
            {},

        # I am starting the Supervisor counter at zero.
        "turn_count":
            0,

        # I am initially allowing up to 10 Supervisor turns.
        "turn_ceiling":
            10,

        #added new
        "planner_attempts": 0
    }


    print(
        "\n===== STARTING LANGGRAPH =====\n"
    )


    # HW2 specifically asks me to use .stream()
    # so I can observe the output from each graph step.
    for event in graph.stream(initial_state):

        print(
            "\n--- GRAPH EVENT ---"
        )

        print(
            json.dumps(
                event,
                indent=2,
                default=str
            )
        )


    print(
        "\n===== GRAPH FINISHED ====="
    )   


if __name__ == "__main__":
    main()    