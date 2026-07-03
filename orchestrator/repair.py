"""Message sequence repair — ensure strict role alternation for tool calls."""


def repair_message_sequence(messages: list) -> list:
    """Ensure strict role alternation: assistant(tool_calls) -> tool -> tool -> ...

    Also strips orphaned tool_calls (IDs without matching tool responses)
    and orphaned tool messages (responses without a matching assistant).

    If a non-tool message (like a user message injected by a tool) is found
    while an assistant message is still waiting for its tool responses,
    that non-tool message is pushed AFTER all the tool responses.

    Returns the reordered and cleaned message list.
    """
    if not messages:
        return messages

    # ── Phase 1: Collect all valid tool_call_ids ──
    all_tool_ids = set()
    for msg in messages:
        if msg.get("role") == "tool":
            tc_id = msg.get("tool_call_id", "")
            if tc_id:
                all_tool_ids.add(tc_id)

    # ── Phase 2: Strip orphaned tool_calls from assistant messages ──
    cleaned = []
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            valid_tcs = [
                tc for tc in msg["tool_calls"]
                if tc.get("id", "") in all_tool_ids
            ]
            if not valid_tcs:
                # No tool_call match — if content exists, treat as plain message
                if msg.get("content"):
                    cleaned.append({"role": "assistant", "content": msg["content"]})
                # Yoksa tamamen at
                continue
            elif len(valid_tcs) < len(msg["tool_calls"]):
                # Some are orphaned — keep only valid ones
                msg = {**msg, "tool_calls": valid_tcs}
                cleaned.append(msg)
            else:
                cleaned.append(msg)
        else:
            cleaned.append(msg)

    # ── Phase 3: Reorder — ensure tool responses follow their assistant ──
    reordered = []
    pending_non_tools = []
    active_tool_calls = set()

    for msg in cleaned:
        role = msg.get("role", "")

        if role == "assistant" and msg.get("tool_calls"):
            # If we had any pending non-tools from a previous block, flush them
            if pending_non_tools and not active_tool_calls:
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
                # Orphaned tool message — discard (no matching assistant)
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
