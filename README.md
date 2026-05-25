# Winnougan Prompt Cycler 📝

A dead-simple ComfyUI custom node that loads a `.txt` file of prompts and cycles through them one per run — automatically. No babysitting required.

Made by [Lord Winnougan](https://www.patreon.com/c/u5867556) · Support on Patreon ⭐

---

## What it does

Point it at a `.txt` file. Hit Queue once. It generates one image per prompt, auto-requeues itself, and stops when the list is done.

That's it.

---

## Installation

### Via ComfyUI Manager (recommended)
Search for **Winnougan Prompt Cycler** in ComfyUI Manager and install.

### Manual
```bash
cd ComfyUI/custom_nodes
git clone https://github.com/Winnougan/Comfy_Prompt_Cycler.git winnougan_prompt_cycler
```
Then restart ComfyUI.

---

## Setup

### 1. Prepare your `.txt` file

Separate each prompt with a **blank line**:

```
Masterpiece, 1girl, eating burger

Masterpiece, 1girl, eating pizza

Masterpiece, 1girl, swimming in pool
```

Save it anywhere on your PC, e.g. `C:\Users\you\Downloads\prompts.txt`

### 2. Add the node

Right-click canvas → Add Node → **Winnougan → Prompt → Winnougan Prompt Cycler 📝**

### 3. Wire it up

```
[Winnougan Prompt Cycler 📝]
        ↓ prompt
[CLIP Text Encode]  ← your positive prompt node
```

That's the only wire needed. Your negative prompt stays unchanged.

### 4. Set the path

Paste the full path to your `.txt` file into the `txt_file` field.

### 5. Hit Queue once and walk away

---

## Node options

| Option | Description |
|---|---|
| `txt_file` | Full path to your prompts `.txt` file |
| `Reset` | Flip to **Reset to first** to start over from prompt 1 |
| `Loop` | When **Loop ON**, restarts from the beginning after the last prompt instead of stopping |
| `Auto requeue` | When **ON**, automatically re-queues after each image — no need to click Queue manually |

---

## Outputs

| Output | Type | Description |
|---|---|---|
| `prompt` | STRING | The current prompt — wire to your positive CLIP Text Encode |
| `current_index` | INT | Which prompt we're on (0-based) |
| `total_prompts` | INT | Total number of prompts in the file |
| `is_done` | BOOLEAN | True when the last prompt has been processed |

---

## Tips

- Prompts can be as long or short as you like — just make sure there's a blank line between each one
- The node saves its position between sessions, so if ComfyUI crashes mid-run it picks up where it left off
- Flip **Reset** to true and queue once to start over, then flip it back to Continue
- Use **Loop ON** to keep generating in a cycle indefinitely — great for testing

---

## License

MIT
