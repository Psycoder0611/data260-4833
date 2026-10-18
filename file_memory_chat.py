"""Command-line chat that uses AGENT.md and MEMORY.md as file-based memory (HW6 Part 4)."""
import argparse

from hw6 import config, file_memory, llm


def chat_text(messages):
    """Send messages to the local model and return only the reply text."""
    return llm.chat(messages)["content"]


def run_line(line, history):
    """Handle one input line: a slash command or a normal chat message."""
    if line.startswith("/"):
        return file_memory.handle_command(line, history, chat_text)
    memory_text = file_memory.load_memory_md()
    required, reasons = file_memory.needs_consolidation(memory_text)
    system_prompt = file_memory.build_system_prompt(file_memory.load_agent_md(), memory_text)
    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": line}]
    reply = chat_text(messages)
    history.append({"role": "user", "content": line})
    history.append({"role": "assistant", "content": reply})
    file_memory.save_recent_message("user", line)
    file_memory.save_recent_message("assistant", reply)
    notice = f"\n[note] MEMORY.md needs consolidation: {'; '.join(reasons)}. Type /compact." if required else ""
    return reply + notice


def main():
    """Run an interactive loop, or one line with --once."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", help="run a single message or /command and exit")
    args = parser.parse_args()
    history = file_memory.load_recent_conversation()
    print(f"File-based memory chat | model {config.MODEL_NAME} | type /help for commands, /quit to exit")
    if args.once:
        print(run_line(args.once, history))
        return
    required, reasons = file_memory.needs_consolidation(file_memory.load_memory_md())
    if required:
        print(f"[note] MEMORY.md needs consolidation: {'; '.join(reasons)}. Type /compact.")
    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if line in ("/quit", "/exit"):
            break
        if line:
            print(run_line(line, history))


if __name__ == "__main__":
    main()
