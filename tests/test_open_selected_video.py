import ast
from pathlib import Path


def test_open_selected_video_folder_uses_resolved_workflow_key():
    source = Path("app/ui/main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    main_window = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "MainWindow")
    open_selected = next(
        node for node in main_window.body if isinstance(node, ast.FunctionDef) and node.name == "open_selected"
    )
    video_path_assignment = next(
        node
        for node in ast.walk(open_selected)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "video_path" for target in node.targets)
    )
    call = video_path_assignment.value

    assert isinstance(call, ast.Call)
    workflow_keyword = next(keyword for keyword in call.keywords if keyword.arg == "workflow_key")
    assert isinstance(workflow_keyword.value, ast.Name)
    assert workflow_keyword.value.id == "workflow_key"
