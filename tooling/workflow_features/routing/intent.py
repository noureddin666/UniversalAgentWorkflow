from __future__ import annotations


INTENT_SIGNALS = {
    "diagnosis": ("diagnose", "investigate", "root cause", "شخّص", "حقق", "سبب المشكلة"),
    "review": ("review", "audit", "assess", "راجع", "تدقيق", "قيّم"),
    "refactor": ("refactor", "restructure", "cleanup", "إعادة هيكلة", "نظف"),
    "bugfix": ("fix", "bug", "regression", "broken", "أصلح", "خلل", "مشكلة"),
    "discovery": ("discover", "inventory", "map", "اكتشف", "احصر", "خريطة"),
}


def infer_intent(task: str) -> str:
    normalized = task.casefold()
    for intent, signals in INTENT_SIGNALS.items():
        if any(signal in normalized for signal in signals):
            return intent
    return "feature"
