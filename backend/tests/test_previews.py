"""Pure functions behind the preview registry: next_free and merge_previews."""

from app.environments.workspace import ListeningPort, merge_previews, next_free


def test_next_free_picks_first_open_port():
    assert next_free(range(3000, 3010), {3000, 3001}) == 3002


def test_next_free_none_when_all_taken():
    assert next_free(range(3000, 3002), {3000, 3001}) is None


def test_merge_previews_registered_first_newest_first():
    registry = [
        {"port": 3000, "title": "First", "path": "/", "agent_node_id": "a", "created_at": "t1"},
        {"port": 3001, "title": "Second", "path": "/app", "agent_node_id": "a", "created_at": "t2"},
    ]
    listening = [
        ListeningPort(port=3000, pid=1, command="node", local_only=False),
        ListeningPort(port=3001, pid=1, command="node", local_only=False),
    ]
    rows = merge_previews(registry, listening, lambda p: f"https://x-{p}")

    assert [r["id"] for r in rows] == ["3001", "3000"]
    assert all(r["published"] and r["live"] for r in rows)


def test_merge_previews_drops_dead_registered_port():
    registry = [
        {"port": 3000, "title": "Gone", "path": "/", "agent_node_id": None, "created_at": None}
    ]
    assert merge_previews(registry, [], lambda p: f"https://x-{p}") == []


def test_merge_previews_unregistered_titled_by_served_folder():
    cmd = "python3 -m http.server 8081 --bind 0.0.0.0 --directory /home/user/workspace/site"
    listening = [ListeningPort(port=8081, pid=3, command=cmd, local_only=False)]
    assert merge_previews([], listening, lambda p: "u")[0]["title"] == "site"


def test_merge_previews_unregistered_listening_port_appended():
    listening = [ListeningPort(port=8080, pid=2, command="", local_only=False)]
    rows = merge_previews([], listening, lambda p: f"https://x-{p}")

    assert rows == [
        {
            "id": "8080",
            "title": None,
            "port": 8080,
            "path": "/",
            "url": "https://x-8080",
            "live": True,
            "published": False,
            "agent_node_id": None,
            "created_at": None,
        }
    ]


def test_merge_previews_registered_port_not_duplicated_when_listening():
    registry = [
        {"port": 3000, "title": "App", "path": "/", "agent_node_id": None, "created_at": None}
    ]
    listening = [ListeningPort(port=3000, pid=1, command="node", local_only=False)]
    rows = merge_previews(registry, listening, lambda p: f"https://x-{p}")

    assert len(rows) == 1
    assert rows[0]["published"] is True


def test_fallback_title_uses_workspace_cwd_else_process():
    from app.environments.workspace import fallback_title

    in_ws = ListeningPort(
        port=3000,
        pid=1,
        command="python3 -m http.server 3000",
        local_only=False,
        cwd="/home/user/workspace/abc",
    )
    elsewhere = ListeningPort(
        port=8000, pid=1, command="python3 -m http.server", local_only=False, cwd="/home/user"
    )
    assert fallback_title(in_ws) == "abc"
    assert fallback_title(elsewhere) == "python3 -m http.server"


# -- folder servers: avoid Python's directory listing --------------------------


def _folder(port, folder="/home/user/deck"):
    cmd = f"python3 -m http.server {port} --directory {folder}"
    return ListeningPort(port=port, pid=1, command=cmd, local_only=False)


def _fix(registry, listening, html):
    from app.environments.workspace import fix_folder_paths

    rows = merge_previews(registry, listening, lambda p: f"https://x-{p}")
    return fix_folder_paths(rows, listening, html)


def test_fix_unpublished_folder_picks_first_html():
    html = {"/home/user/deck": ["Zed.html", "deck.html"]}
    assert _fix([], [_folder(8080)], html)[0]["path"] == "/deck.html"


def test_fix_index_html_keeps_root():
    html = {"/home/user/deck": ["deck.html", "index.html"]}
    assert _fix([], [_folder(8080)], html)[0]["path"] == "/"


def test_fix_no_html_drops_unpublished_keeps_published():
    html = {"/home/user/deck": []}
    assert _fix([], [_folder(8080)], html) == []
    registry = [{"port": 8080, "title": "t", "path": "/"}]
    assert len(_fix(registry, [_folder(8080)], html)) == 1


def test_fix_published_root_repointed_but_app_path_and_node_untouched():
    html = {"/home/user/deck": ["limitations.html"]}
    registry = [
        {"port": 8080, "title": "a", "path": "/"},
        {"port": 8081, "title": "b", "path": "/app"},
    ]
    node = ListeningPort(port=5173, pid=2, command="node vite", local_only=False)
    rows = _fix(registry, [_folder(8080), _folder(8081), node], {**html})
    by_port = {r["port"]: r["path"] for r in rows}
    assert by_port == {8080: "/limitations.html", 8081: "/app", 5173: "/"}


def test_fix_uses_cwd_when_no_directory_flag():
    p = ListeningPort(
        port=8080,
        pid=1,
        command="python3 -m http.server 8080",
        local_only=False,
        cwd="/home/user/x",
    )
    assert _fix([], [p], {"/home/user/x": ["a.html"]})[0]["path"] == "/a.html"


def test_fix_unknown_directory_leaves_rows():
    assert _fix([], [_folder(8080)], {})[0]["path"] == "/"


def test_merge_previews_republish_of_same_page_shows_once():
    # Scoping re-run: new server on 3003, new title, same folder and file as 3000.
    folder = "/home/user/workspace/agent1"
    serve = lambda port: ListeningPort(  # noqa: E731
        port=port,
        pid=port,
        command=f"python3 -m http.server {port} --bind 0.0.0.0 --directory {folder}",
        local_only=False,
    )
    registry = [
        {"title": "Scope report", "port": 3000, "path": "/report.html"},
        {"title": "Other page", "port": 3001, "path": "/other.html"},
        {"title": "Scope report rev 2", "port": 3003, "path": "/report.html"},
    ]
    listening = [serve(3000), serve(3001), serve(3003)]
    rows = merge_previews(registry, listening, lambda p: f"https://x-{p}")
    assert [(r["port"], r["title"]) for r in rows] == [
        (3003, "Scope report rev 2"),
        (3001, "Other page"),
    ]


def test_merge_previews_same_path_different_folders_both_kept():
    ws = "/home/user/workspace"
    a = ListeningPort(port=3000, pid=1, command="node", local_only=False, cwd=f"{ws}/a")
    b = ListeningPort(port=3001, pid=2, command="node", local_only=False, cwd=f"{ws}/b")
    registry = [
        {"title": "A", "port": 3000, "path": "/"},
        {"title": "B", "port": 3001, "path": "/"},
    ]
    assert len(merge_previews(registry, [a, b], lambda p: "u")) == 2
