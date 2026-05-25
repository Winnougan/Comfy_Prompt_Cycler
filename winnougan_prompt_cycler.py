import json
import time
import threading
import urllib.request
from pathlib import Path

STATE_FILE = Path(__file__).parent / "prompt_cycler_state.json"


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


def requeue_via_api(delay: float = 2.0):
    def _post():
        time.sleep(delay)
        try:
            with urllib.request.urlopen("http://127.0.0.1:8188/history?max_items=1") as r:
                history = json.loads(r.read().decode("utf-8"))
            if not history:
                return
            last_id     = list(history.keys())[0]
            prompt_data = history[last_id]["prompt"]
            client_id   = prompt_data[1]
            nodes       = prompt_data[2]
            extra       = prompt_data[3] if len(prompt_data) > 3 else {}
            payload = json.dumps({"client_id": client_id, "prompt": nodes, "extra_data": extra}).encode("utf-8")
            req = urllib.request.Request(
                "http://127.0.0.1:8188/prompt",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if "prompt_id" in result:
                    print(f"[WinnouganPromptCycler] ✅ Auto-requeued → {result['prompt_id']}")
                else:
                    print(f"[WinnouganPromptCycler] ⚠️  Requeue response: {result}")
        except Exception as e:
            print(f"[WinnouganPromptCycler] ⚠️  Auto-requeue failed: {e}")
            print("[WinnouganPromptCycler]    → Use Auto Queue in the ComfyUI toolbar as fallback.")
    threading.Thread(target=_post, daemon=True).start()


class WinnouganPromptCycler:
    """
    Load a .txt file of prompts separated by blank lines.
    Each run sends the next prompt to your positive CLIP Text Encode node.
    Auto-requeues until all prompts are done, then stops.
    """

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
            }
        }

    RETURN_TYPES  = ("STRING", "INT", "INT", "BOOLEAN")
    RETURN_NAMES  = ("prompt", "current_index", "total_prompts", "is_done")
    FUNCTION      = "cycle"
    CATEGORY      = "Winnougan/Prompt"
    OUTPUT_NODE   = False

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def cycle(self, txt_file: str, reset: bool, loop: bool, auto_requeue: bool):
        if reset:
            clear_state()
            print("[WinnouganPromptCycler] Reset — starting from first prompt.")

        prompts = parse_prompts(txt_file)
        total   = len(prompts)

        if total == 0:
            raise ValueError("[WinnouganPromptCycler] No prompts found. Separate prompts with a blank line.")

        idx = load_state(txt_file)

        if idx >= total:
            if loop:
                print("[WinnouganPromptCycler] 🔁 Looping back to start.")
                idx = 0
                clear_state()
            else:
                print("[WinnouganPromptCycler] ✅ All prompts done!")
                return (prompts[-1], total - 1, total, True)

        prompt  = prompts[idx]
        is_done = (idx + 1) >= total

        print(f"[WinnouganPromptCycler] {idx + 1}/{total}: {prompt[:60]}{'...' if len(prompt) > 60 else ''}")

        save_state(txt_file, idx + 1)

        if auto_requeue and not (is_done and not loop):
            requeue_via_api(delay=2.0)

        return (prompt, idx, total, is_done)


NODE_CLASS_MAPPINGS = {
    "WinnouganPromptCycler": WinnouganPromptCycler,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WinnouganPromptCycler": "Winnougan Prompt Cycler 📝",
}
