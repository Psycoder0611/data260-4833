# HW5 AI Use

## 1. What I used an AI assistant for and what I did myself

I used an AI assistant mainly for guidance while organizing the homework, understanding the assignment requirements, debugging errors, and drafting some starter code structures. I personally ran all commands, created and modified the project files, tested the FastAPI and React application, executed MCP tools in MCP Inspector, ran the fault-injection experiments, tested the offline tool runner, and executed the local Ollama agent scenarios.

## 2. One AI-produced output that was wrong or independently verified

One issue occurred while setting up the MCP server. The initial suggested MCP import did not match the version of the MCP package installed in my environment, which caused the server to fail when starting through MCP Inspector.

## 3. How I detected or verified the problem

I detected the problem from the terminal traceback and from MCP Inspector showing that the server failed to start. I also tested the server directly from the terminal and checked the installed MCP behavior before changing the implementation.

## 4. What I changed and why it works now

I updated the MCP server code to use the import and server class supported by my installed MCP version and launched the Inspector using the working `uv run mcp dev` command. After the change, the server connected successfully and all required MCP tools could be executed and validated in MCP Inspector.