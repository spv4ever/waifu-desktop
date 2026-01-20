from __future__ import annotations

import json
import os
from pathlib import Path


def main():
    path = Path(os.getenv("COMFYUI_WORKFLOW_JSON", "resources/workflows/waifu_workflow.json"))
    wf = json.loads(path.read_text(encoding="utf-8"))

    print("Workflow nodes (node_id -> class_type / inputs keys):\n")
    # formato típico: { "10": {"class_type":"CLIPTextEncode","inputs":{...}}, ...}
    for node_id, node in wf.items():
        if not isinstance(node, dict):
            continue
        ctype = node.get("class_type", "?")
        inputs = node.get("inputs", {}) or {}
        keys = ", ".join(sorted(inputs.keys()))
        print(f"- {node_id}: {ctype} | inputs: {keys}")


if __name__ == "__main__":
    main()
