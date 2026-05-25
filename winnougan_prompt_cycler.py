import json
import time
import threading
import urllib.request
import uuid
from pathlib import Path
from server import PromptServer

STATE_FILE  = Path(__file__).parent / "prompt_cycler_state.json"
LAST_PROMPT = {}


def load_state(txt_path: str) -> int:
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            if data.get("file") == txt_path:
                return int(data.get("index", 0))
        except Exception:
            pass
    return 0


def save_state(txt_path: str, index: int):
    STATE_FILE.write_text(json.dumps({"file": txt_path, "index": index}))


def clear_state():
    if STATE_FILE.exists():
        STATE_FILE.unlink()


def parse_prompts(txt_path: str) -> list:
    path = Path(txt_path)
    if not path.exists():
        raise ValueError(f"[WinnouganPromptCycler] File not found: {txt_path}")
    raw    = path.read_text(encoding="utf-8")
    blocks = [b.strip() for b in raw.split("\n\n") if b.strip()]
    return blocks


def find_cycler_node_id(nodes: dict) -> str | None:
    """Find the WinnouganPromptCycler node id inside the prompt nodes dict."""
    for node_id, node_data in nodes.items():
        if isinstance(node_data, dict):
            class_type = node_data.get("class_type", "")
            if class_type == "WinnouganPromptCycler":
                return node_id
    return None


def requeue_via_api(snapshot: dict, delay: float = 1.0):
    """
    Re-queue the workflow. The state file is already advanced,
    so the cycler node will read the next prompt naturally on next execution.
    We do NOT patch the prompt text — we let the node do it fresh.
    """
    def _post():
        time.sleep(delay)
        try:
            if not snapshot or not snapshot.get("nodes"):
                print("[WinnouganPromptCycler] ⚠️  Snapshot empty, cannot requeue.")
                return

            # Deep copy nodes so we don't mutate the original
            import copy
            nodes = copy.deepcopy(snapshot["nodes"])

            # Find our node and clear its cached inputs so ComfyUI
            # doesn't serve a stale cached output — force a fresh execution
            cycler_id = find_cycler_node_id(nodes)
            if cycler_id:
                # Flip reset to False in case it was True, and inject a unique
                # run_id input that guarantees IS_CHANGED fires
                if "inputs" in nodes[cycler_id]:
                    nodes[cycler_id]["inputs"]["reset"] = False
                    # This extra key is ignored by the node but busts the cache
                    nodes[cycler_id]["inputs"]["_run_id"] = str(uuid.uuid4())
            else:
                print("[WinnouganPromptCycler] ⚠️  Could not find cycler node in snapshot.")

            payload = json.dumps({
                "client_id":  snapshot.get("client_id", ""),
                "prompt":     nodes,
                "extra_data": snapshot.get("extra", {}),
            }).encode("utf-8")

            req = urllib.request.Request(
                "http://127.0.0.1:8188/prompt",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if "prompt_id" in result:
                    print(f"[WinnouganPromptCycler] ✅ Requeued → {result['prompt_id']}")
                else:
                    print(f"[WinnouganPromptCycler] ⚠️  Requeue response: {result}")
        except Exception as e:
            print(f"[WinnouganPromptCycler] ⚠️  Requeue failed: {e}")

    threading.Thread(target=_post, daemon=True).start()


def _setup_prompt_capture():
    try:
        server = PromptServer.instance
        queue  = server.prompt_queue

        def make_patcher(original):
            def patched(item, *args, **kwargs):
                try:
                    if isinstance(item, (list, tuple)) and len(item) >= 3:
                        nodes = item[2]
                        if isinstance(nodes, dict) and len(nodes) > 0:
                            LAST_PROMPT["client_id"] = item[1] if len(item) > 1 else ""
                            LAST_PROMPT["nodes"]     = nodes
                            LAST_PROMPT["extra"]     = item[3] if len(item) > 3 else {}
                            print(f"[WinnouganPromptCycler] 📸 Captured {len(nodes)} nodes")
                except Exception as ex:
                    print(f"[WinnouganPromptCycler] Capture warning: {ex}")
                return original(item, *args, **kwargs)
            return patched

        for method_name in ("put", "put_nowait"):
            if hasattr(queue, method_name):
                setattr(queue, method_name, make_patcher(getattr(queue, method_name)))

    except Exception as e:
        print(f"[WinnouganPromptCycler] Prompt capture setup skipped: {e}")

_setup_prompt_capture()


class WinnouganPromptCycler:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "txt_file": (
                    "STRING",
                    {
                        "default": r"C:\Users\uthma\Downloads\prompts.txt",
                        "multiline": False,
                    },
                ),
                "reset": (
                    "BOOLEAN",
                    {"default": False, "label_on": "Reset to first", "label_off": "Continue"},
                ),
                "loop": (
                    "BOOLEAN",
                    {"default": False, "label_on": "Loop ON", "label_off": "Loop OFF"},
                ),
                "auto_requeue": (
                    "BOOLEAN",
                    {"default": True, "label_on": "Auto requeue ON", "label_off": "Manual queue"},
                ),
            },
            # Hidden input — injected by requeue to bust cache, ignored by cycle()
            "hidden": {
                "_run_id": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES  = ("STRING", "INT", "INT", "BOOLEAN")
    RETURN_NAMES  = ("prompt", "current_index", "total_prompts", "is_done")
    FUNCTION      = "cycle"
    CATEGORY      = "Winnougan/Prompt"
    OUTPUT_NODE   = True

    @classmethod
    def IS_CHANGED(cls, txt_file, reset, loop, auto_requeue, _run_id=""):
        # State file tells us the real index — hash it so IS_CHANGED
        # returns a new value every time the index advances
        try:
            if STATE_FILE.exists():
                return STATE_FILE.read_text()
        except Exception:
            pass
        return str(uuid.uuid4())

    def cycle(self, txt_file: str, reset: bool, loop: bool, auto_requeue: bool, _run_id: str = ""):
        if reset:
            clear_state()
            print("[WinnouganPromptCycler] Reset — starting from first prompt.")

        prompts = parse_prompts(txt_file)
        total   = len(prompts)

        if total == 0:
            raise ValueError("[WinnouganPromptCycler] No prompts found. Separate with blank lines.")

        idx = load_state(txt_file)

        if idx >= total:
            if loop:
                print("[WinnouganPromptCycler] 🔁 Looping back to start.")
                idx = 0
                clear_state()
            else:
                print(f"[WinnouganPromptCycler] ✅ All {total} prompts done — stopping.")
                return (prompts[-1], total - 1, total, True)

        prompt  = prompts[idx]
        is_done = (idx + 1) >= total

        print(f"[WinnouganPromptCycler] ▶ {idx + 1}/{total}: {prompt[:80]}{'...' if len(prompt) > 80 else ''}")

        # Advance BEFORE requeue so next run reads the next index
        save_state(txt_file, idx + 1)

        if auto_requeue and not (is_done and not loop):
            snapshot = {
                "client_id": LAST_PROMPT.get("client_id", ""),
                "nodes":     dict(LAST_PROMPT.get("nodes", {})),
                "extra":     dict(LAST_PROMPT.get("extra", {})),
            }
            if snapshot["nodes"]:
                requeue_via_api(snapshot, delay=1.0)
            else:
                print("[WinnouganPromptCycler] ⚠️  No snapshot yet — queue manually once to start the chain.")

        return (prompt, idx, total, is_done)


NODE_CLASS_MAPPINGS = {
    "WinnouganPromptCycler": WinnouganPromptCycler,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WinnouganPromptCycler": "Winnougan Prompt Cycler 📝",
}