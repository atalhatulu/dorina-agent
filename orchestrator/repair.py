"""Message sequence repair — ensure strict role alternation for tool calls."""


def repair_message_sequence(messages: list) -> list:
    """Ensure strict role alternation: assistant(tool_calls) -> tool -> tool -> ...

    If a non-tool message (like a user message injected by a tool) is found
    while an assistant message is still waiting for its tool responses,
    that non-tool message is pushed AFTER all the tool responses.

    Returns the reordered message list.
    """
    if not messages:
        return messages

    reordered = []
    pending_non_tools = []
    active_tool_calls = set()

    for msg in messages:
        role = msg.get("role", "")

        if role == "assistant" and msg.get("tool_calls"):
            # If we had any pending non-tools from a previous block, flush them
            reordered.extend(pending_non_tools)
            pending_non_tools = []

            reordered.append(msg)
            active_tool_calls = {tc.get("id", "") for tc in msg["tool_calls"]}

        elif role == "tool":
            tc_id = msg.get("tool_call_id", "")
            if tc_id in active_tool_calls:
                reordered.append(msg)
                active_tool_calls.discard(tc_id)
            else:
                # Orphaned tool message, ignore or just append
                pass

            # If all tool calls for the current assistant are fulfilled, flush pending non-tools
            if not active_tool_calls and pending_non_tools:
                reordered.extend(pending_non_tools)
                pending_non_tools = []

        else:
            # User or normal Assistant message
            if active_tool_calls:
                # We are in the middle of fulfilling tool calls! Buffer it.
                pending_non_tools.append(msg)
            else:
                # Safe to append immediately
                reordered.append(msg)

    # Flush any remaining pending messages at the end
    if pending_non_tools:
        reordered.extend(pending_non_tools)

    return reordered
