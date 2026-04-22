import os
from pathlib import Path

def check_file(path):
    exists = os.path.exists(path)
    print(f"[{'x' if exists else ' '}] {path}")
    return exists

print("--- Backend Routes ---")
# Check if routes are imported in api/main.py
with open("api/main.py", "r", encoding="utf-8") as f:
    main_content = f.read()
    print(f"[{'x' if 'exports_router' in main_content else ' '}] exports_router in main.py")
    print(f"[{'x' if 'router as hooks_router' in main_content else ' '}] hooks_router in main.py")

print("\n--- Feature 1: CapCut Bridge ---")
check_file("api/routes/exports.py")
with open("api/routes/exports.py", "r", encoding="utf-8") as f:
    content = f.read()
    print(f"[{'x' if 'capcut-bridge' in content else ' '}] GET /capcut-bridge endpoint exists")

print("\n--- Feature 2: Hook Variation Engine ---")
check_file("api/routes/hooks.py")
check_file("services/llm_integration.py")
with open("services/llm_integration.py", "r", encoding="utf-8") as f:
    content = f.read()
    print(f"[{'x' if 'generate_hook_variants' in content else ' '}] generate_hook_variants() logic exists")

print("\n--- Feature 3: Smart Transcript Handles ---")
check_file("api/routes/clip_studio.py")
with open("api/routes/clip_studio.py", "r", encoding="utf-8") as f:
    content = f.read()
    print(f"[{'x' if 'adjust' in content else ' '}] PATCH /adjust endpoint exists")
with open("web/components/clip-timeline-editor.tsx", "r", encoding="utf-8") as f:
    content = f.read()
    print(f"[{'x' if 'onMouseDown' in content and 'onMouseEnter' in content else ' '}] Click-and-drag logic exists in UI")

print("\n--- Feature 5: Swipe PWA ---")
check_file("web/app/jobs/[jobId]/review/page.tsx")
check_file("web/components/swipe-deck.tsx")

print("\n--- Multi-Goal Engine ---")
with open("services/clip_detector.py", "r", encoding="utf-8") as f:
    content = f.read()
    print(f"[{'x' if 'custom_prompt_instruction' in content else ' '}] Custom instruction logic in detector")

print("\n--- Revert Checklist ---")
files_to_check = [
    "api/dependencies/auth.py",
    "api/routes/billing.py",
    "web/middleware.ts",
    "web/components/auth-provider.tsx"
]
for f in files_to_check:
    with open(f, "r", encoding="utf-8") as file:
        content = file.read()
        print(f"[{'x' if 'REVERT BEFORE DEPLOY' in content else ' '}] Revert marker in {f}")
