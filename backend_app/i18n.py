"""英文版的词表。

比赛有英文评委，看不懂就没法评。所以英文不能只是「把界面翻一遍」——
用户真正读到的那些话（我猜你更接近什么、为什么是这里、代价是什么）
是后端生成的，这一份必须跟着一起有英文。

翻译的标准和中文一样，不是字面对应：
小在说话是短句、白话、身体感，不抒情、不诊断、不承诺。
英文里同样如此——"you said you're running on empty"，不是
"you are experiencing low energy levels"。
"""

from __future__ import annotations

from typing import Literal


Lang = Literal["zh", "en"]

STATE_LABELS_EN: dict[str, str] = {
    "low": "running on empty",
    "quiet": "need it quiet",
    "noisy": "can't stop thinking",
    "spark": "want something new",
    "tired": "tired but wired",
    "empty": "feeling hollow",
    "tight": "wound tight",
    "near": "want someone nearby",
    "fresh": "need a change of scene",
    "okay": "doing okay",
}

NEED_LABELS_EN: dict[str, str] = {
    "hide": "not be seen",
    "sit": "sit for a long time",
    "walk": "keep walking",
    "free": "not spend much",
    "green": "see something green",
    "new": "see something new",
    "sound": "hear something",
    "people": "people around",  # ClarifyOption.label 上限 24 字，别超
    "loud": "somewhere loud",
    "slow": "slow down",
    "hands": "keep my hands busy",
    "breathe": "breathe",
    "nothing": "not decide anything",
}

AVOID_LABELS_EN: dict[str, str] = {
    "people": "no people",
    "loud": "nothing loud",
    "sound": "no noise",
    "hands": "nothing to do",
    "new": "nothing new",
    "walk": "no long walk",
    "green": "no greenery",
}

# 12 个标签维度。卡片上的「这里：安静、可久待」用的就是这些。
TAG_LABELS_EN: dict[str, str] = {
    "q": "quiet",
    "g": "green",
    "c": "crowded",
    "s": "fine alone",
    "co": "lived-in",
    "e": "new to you",
    "r": "restorative",
    "cr": "sparks something",
    "l": "lively",
    "st": "stay as long as you like",
    "cp": "costs money",
    "w": "room to walk",
}

LOW_TAG_LABELS_EN: dict[str, str] = {
    "q": "a bit of noise",
    "g": "not much green",
    "c": "not crowded",
    "s": "better with someone",
    "co": "quiet streets",
    "e": "nothing new",
    "r": "not especially restful",
    "cr": "nothing to figure out",
    "l": "not lively",
    "st": "not a place to linger",
    "cp": "easy on the wallet",
    "w": "not far to walk",
}

RELIEF_LABELS_EN: dict[str, str] = {
    "now": "you can be there now",
    "near": "about twenty minutes",
    "later": "a bit of a trip · could keep for another day",
}

OPEN_LABELS_EN: dict[str, str] = {
    "always_open": "No door. Open whenever.",
    "unknown": "Opening hours unclear — worth checking first.",
}

UI_EN: dict[str, str] = {
    "chain_said": "You said",
    "chain_here": "Here",
    "chain_unsure": "This one's only roughly close — I'm not certain",
    "no_tradeoff": "Nothing obvious it asks of you",
    "tradeoff_lead": "What it asks of you: ",
    "relaxed_note": "I couldn't find anything good within {minutes} minutes. "
                    "These are the closest — all of them are further than that. Up to you.",
    "all_shut": "Not much is open at this hour; most of these are probably closed. "
                "Want to go somewhere without a door instead?",
    "no_good_match": "I'm not confident about these. Here's the closest one — say so if it's wrong.",
    "safety": "Right now I care more about whether you're safe. Please reach someone you trust; "
              "if you might hurt yourself soon, contact local emergency services right away.",
    "ack": "I heard you. You don't have to explain it — I'll narrow things down from what you just said.",
    "restate": "My guess is you're closer to 「{label}」. Say so if I got it wrong and I'll switch.",
    "restate_with_need": "My guess is you're closer to 「{label}」, and you want somewhere you can {needs}. "
                         "Say so if I got it wrong and I'll switch.",
}


CLARIFY_EN: dict[str, tuple[str, tuple[tuple[str, str], ...]]] = {
    "social_mode": (
        "Just one question: do you want to be alone, or around people without having to talk?",
        (("alone", "Alone"), ("low_contact", "People, no talking"), ("either", "Either")),
    ),
    "max_travel_minutes": (
        "Just one question: how long are you willing to be on the way?",
        (("10", "Under 10 min"), ("25", "About 20 min"), ("60", "Further is fine")),
    ),
    "budget_level": (
        "Just one question: do you want to spend anything today?",
        (("free", "Nothing"), ("low", "A little"), ("unknown", "Either")),
    ),
}

# 四环纠错的选项。和中文一样：这些是身体感觉，不是病名。
CORRECTION_CHIPS_EN: tuple[tuple[str, str], ...] = (
    ("tight", "wound tight"), ("noisy", "can't stop thinking"), ("tired", "tired but wired"),
    ("empty", "feeling hollow"), ("near", "want someone nearby"), ("fresh", "need a change"),
    ("quiet", "need it quiet"), ("low", "running on empty"), ("spark", "want something new"),
    ("okay", "doing okay"),
)

CONSTRAINT_CORRECTIONS_EN: tuple[tuple[str, str], ...] = (
    ("max_travel_minutes:15", "too far — keep it close"),
    ("budget_level:free", "don't want to spend"),
    ("environment:indoor", "want to be indoors"),
    ("environment:outdoor", "want to be outside"),
    ("social_mode:alone", "want to be alone"),
    ("social_mode:with_people", "want people around"),
)


def state_label(mood_id: str, lang: Lang) -> str | None:
    return STATE_LABELS_EN.get(mood_id) if lang == "en" else None


def ui(key: str, lang: Lang, **kwargs: object) -> str | None:
    """英文界面串。zh 返回 None，调用方继续用它原本那句中文。"""
    if lang != "en":
        return None
    text = UI_EN.get(key)
    return text.format(**kwargs) if text and kwargs else text
