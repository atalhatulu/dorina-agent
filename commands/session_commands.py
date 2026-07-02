"""Session management commands: /new, /save, /load, /sessions, /remove, /clean, /ara, /export."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app import DorinaApp


async def cmd_new(app: "DorinaApp", cmd: str) -> None:
    """Start a new session, optionally with a title::

        /new
        /new my-project-name
    """
    from orchestrator.experimental_loop import loop_v2 as loop
    from session.manager import manager
    from core.config import settings
    from ui.display import print_success
    from ui.repl import set_style

    if not hasattr(app, "godmode"):
        app.godmode = False
    loop.reset()
    loop._temp_mode = False
    set_style("")  # normal style'a don
    title = ""
    if len(cmd) > 5:
        title = cmd[5:].strip().strip("\"'")
    session_id = manager.create(
        title=title,
        model=f"{settings.model.provider}/{settings.model.default.split('/')[-1]}",
    )
    print_success(f"Yeni oturum: {title or session_id}")


async def cmd_temp(app: "DorinaApp", cmd: str) -> None:
    """Start a temp (no-save) session::

        /temp
    """
    from orchestrator.experimental_loop import loop_v2 as loop
    from ui.display import print_info
    from ui.repl import set_style

    loop._temp_mode = True
    set_style("temp")
    print_info("Geçici sohbet modu — kayıt alınmaz, sohbet hafızada tutulur.")


async def cmd_save(app: "DorinaApp", cmd: str) -> None:
    """Save current session with a title::

        /save my-analysis
    """
    from orchestrator.experimental_loop import loop_v2 as loop
    from session.manager import manager
    from ui.display import print_success

    title = cmd[6:].strip()
    manager.save(loop.context.get_messages(), summary=title, title=title)
    if manager.current_id:
        manager.rename(manager.current_id, title)
    print_success(f"Kaydedildi: {title}")


async def cmd_load(app: "DorinaApp", cmd: str) -> None:
    """Load a session by ID, row number, or prefix match::

        /load abc123...
        /load 1
        /load abc
    """
    from orchestrator.experimental_loop import loop_v2 as loop
    from session.manager import manager
    from ui.display import console, print_error

    sid = cmd[6:].strip()
    session = manager.load(sid)
    if not session:
        # Try as row number
        all_sessions = manager.list_sessions(limit=100)
        try:
            idx = int(sid) - 1
            if 0 <= idx < len(all_sessions):
                sid = all_sessions[idx]["id"]
                session = manager.load(sid)
        except ValueError:
            pass
        # Try prefix match
        if not session:
            for s in all_sessions:
                if s["id"].startswith(sid):
                    session = manager.load(s["id"])
                    if session:
                        sid = s["id"]
                        break
    if session:
        loop.context.clear()
        msgs = session.get("messages", [])
        loop.context.messages = msgs
        title = session.get("title", sid)
        # Display entire conversation history
        console.print(f"\n[#D4622A]# Session: {title}[/#D4622A]")
        console.print(f"  [dim]ID: {sid} · {len(msgs)} message(s)[/dim]\n")
        for m in msgs:
            role = m.get("role", "")
            content = m.get("content", "") or ""
            if role == "user":
                console.print(f"  [dim]>[/dim] {content}")
            elif role == "assistant":
                tc = m.get("tool_calls")
                if tc:
                    tool_names = [t["function"]["name"] for t in tc]
                    console.print(f"  [#D4622A]# Dorina #[/#D4622A] [dim]🛠️  {', '.join(tool_names)}[/dim]")
                elif content.strip():
                    console.print(f"  [#D4622A]# Dorina #[/#D4622A]")
                    for line in content.split("\n"):
                        if line.strip():
                            console.print(f"    {line}")
                        else:
                            console.print()
            elif role == "tool":
                tc_id = m.get("tool_call_id", "")[:12]
                name = m.get("name", "?")
                summary_content = content.strip()[:80].replace("\n", " ")
                console.print(f"    [dim]🔧 [{name}] {summary_content}[/dim]")
        console.print(f"\n  [#6bb05d]✓[/#6bb05d] Session loaded. Agent ready — type your message to continue.")
    else:
        print_error(f"Session not found: {sid}")


async def cmd_sessions(app: "DorinaApp", cmd: str) -> None:
    """List all saved sessions::

        /sessions
    """
    from session.manager import manager
    from ui.display import console

    sessions = manager.list_sessions()
    console.print("\n[bold #D4622A]# Session List[/bold #D4622A]")
    console.print(f"  [dim]{'#':<4} {'Title':<28} {'Preview':<33} {'Tur':<5} {'Last Active':<12} ID[/dim]")
    console.print(f"  [dim]{'─'*4:<4} {'─'*28:<28} {'─'*33:<33} {'─'*5:<5} {'─'*12:<12} ────────────[/dim]")
    for i, s in enumerate(sessions, 1):
        title = s["title"][:26] + ".." if len(s["title"]) > 26 else s["title"]
        preview = s.get("summary", "")[:31] + "..." if len(s.get("summary", "")) > 31 else s.get("summary", "")
        tur = s.get("message_count", 0) // 2 + 1
        last_active_raw = s.get("updated_at", s.get("created_at", ""))
        if last_active_raw and len(last_active_raw) >= 16:
            dt = last_active_raw[:16].replace("T", "-").replace(":", "")
            parts = dt.split("-")
            if len(parts) >= 4:
                last_active = f"{parts[2]}-{parts[1]}-{parts[0]}-{parts[3]}"
            else:
                last_active = last_active_raw[:10]
        else:
            last_active = last_active_raw[:10] if last_active_raw else ""
        sid = s["id"][:12]
        console.print(f"  {i:<4} {title:<28} {preview:<33} {tur:<5} {last_active:<12} {sid}")


async def cmd_remove(app: "DorinaApp", cmd: str) -> None:
    """Delete a session by ID, row number, or prefix::

        /remove abc123...
        /remove 1
        /remove abc
    """
    from session.manager import manager
    from ui.display import print_success, print_error

    sid = cmd[8:].strip()
    if not sid:
        print_error("Kullanım: /remove <sıra_no|session_id>")
        return

    session = manager.load(sid)
    if not session:
        all_sessions = manager.list_sessions(limit=100)
        try:
            idx = int(sid) - 1
            if 0 <= idx < len(all_sessions):
                sid = all_sessions[idx]["id"]
                session = manager.load(sid)
        except ValueError:
            pass
        if not session:
            for s in all_sessions:
                if s["id"].startswith(sid):
                    session = manager.load(s["id"])
                    if session:
                        sid = s["id"]
                        break
    if session:
        manager.delete(sid)
        print_success(f"Silindi: {sid}")
    else:
        print_error(f"Session bulunamadı: {sid}")


async def cmd_clean(app: "DorinaApp", cmd: str) -> None:
    """Clean up old sessions::

        /clean          # keep last 5
        /clean all      # delete all
        /clean keep=10  # keep last 10
    """
    from session.manager import manager
    from ui.display import print_success

    args = cmd.split()
    if len(args) > 1:
        if args[1].lower() == "all":
            count = manager.cleanup_old(keep_last=0)
            print_success(f"Tum sessionlar temizlendi ({count} adet)")
        elif args[1].lower().startswith("keep="):
            try:
                keep = int(args[1].split("=")[1])
                count = manager.cleanup_old(keep_last=keep)
                print_success(f"{count} eski session temizlendi. Son {keep} session kaldı.")
            except (ValueError, IndexError):
                count = manager.cleanup_old(keep_last=5)
                print_success(f"{count} eski session temizlendi. Son 5 session kaldı.")
        else:
            count = manager.cleanup_old(keep_last=5)
            print_success(f"{count} eski session temizlendi. Son 5 session kaldı.")
    else:
        count = manager.cleanup_old(keep_last=5)
        print_success(f"{count} eski session temizlendi. Son 5 session kaldı.")


async def cmd_ara(app: "DorinaApp", cmd: str) -> None:
    """Search session history::

        /ara query terms
    """
    from session.manager import manager
    from ui.display import print_table as _pt_search

    query = cmd[5:]
    results = manager.search(query)
    rows = [[r["id"][:20], r["title"], r.get("summary", "")[:50]] for r in results]
    _pt_search("Arama Sonuçları", ["ID", "Başlık", "Özet"], rows)


async def cmd_export(app: "DorinaApp", cmd: str) -> None:
    """Export conversation to a file::

        /export json
        /export md
        /export html
    """
    from orchestrator.experimental_loop import loop_v2 as loop
    from ui.display import print_success, print_error

    fmt = cmd[8:].strip().lower()
    from export.formats import export_json, export_markdown, export_html
    msgs = loop.context.get_messages()
    if fmt == "json":
        path = export_json(msgs)
    elif fmt == "md":
        path = export_markdown(msgs)
    elif fmt == "html":
        path = export_html(msgs)
    else:
        print_error(f"Bilinmeyen format: {fmt} (json/md/html)")
        return
    print_success(f"Dışa aktarıldı: {path}")


async def cmd_session(app: "DorinaApp", cmd: str) -> None:
    """Session management utilities: prune, archive, size::

        /session prune [session_id] [keep=100]
        /session archive [days=7]
        /session size [session_id]
    """
    from session.manager import manager
    from ui.display import print_success, print_error, print_info

    args = cmd.split()[1:]  # skip /session
    if not args:
        print_info("Kullanım: /session prune|archive|size")
        return

    sub = args[0].lower()

    if sub == "prune":
        # /session prune [session_id] [keep=100]
        sid = None
        keep = 100
        for a in args[1:]:
            if a.startswith("keep="):
                try:
                    keep = int(a.split("=")[1])
                except (ValueError, IndexError):
                    pass
            elif not sid:
                sid = a
        if not sid:
            sid = manager.current_id
        if not sid:
            print_error("No active session. Specify a session ID.")
            return
        # Resolve prefix / row number
        session = manager.load(sid)
        if not session:
            all_sessions = manager.list_sessions(limit=100)
            try:
                idx = int(sid) - 1
                if 0 <= idx < len(all_sessions):
                    sid = all_sessions[idx]["id"]
            except ValueError:
                for s in all_sessions:
                    if s["id"].startswith(sid):
                        sid = s["id"]
                        break
        removed = manager.prune_session(sid, keep_last=keep)
        if removed == -1:
            print_error(f"Session not found: {sid}")
        elif removed == 0:
            print_info(f"Session {sid[:16]} — only {keep} messages, nothing to prune.")
        else:
            print_success(f"Pruned {removed} message(s) from {sid[:16]}, keeping last {keep}.")

    elif sub == "archive":
        # /session archive [days=7]
        days = 7
        for a in args[1:]:
            if a.startswith("days="):
                try:
                    days = int(a.split("=")[1])
                except (ValueError, IndexError):
                    pass
        count = manager.archive_old_sessions(days=days)
        if count:
            print_success(f"Archived {count} session(s) older than {days} day(s).")
        else:
            print_info(f"No sessions older than {days} day(s) to archive.")

    elif sub == "size":
        # /session size [session_id]
        sid = args[1] if len(args) > 1 else manager.current_id
        if not sid:
            print_error("No active session. Specify a session ID.")
            return
        # Resolve prefix / row number
        session = manager.load(sid)
        if not session:
            all_sessions = manager.list_sessions(limit=100)
            try:
                idx = int(sid) - 1
                if 0 <= idx < len(all_sessions):
                    sid = all_sessions[idx]["id"]
            except ValueError:
                for s in all_sessions:
                    if s["id"].startswith(sid):
                        sid = s["id"]
                        break
        info = manager.get_session_size(sid)
        if not info["exists"]:
            print_error(f"Session not found: {sid}")
            return
        print_info(f"Session {sid[:16]}: {info['message_count']} messages, "
                   f"{info['bytes_raw']:,} bytes raw, "
                   f"{info['bytes_encrypted']:,} bytes encrypted")

    else:
        print_error(f"Unknown session subcommand: {sub}")
