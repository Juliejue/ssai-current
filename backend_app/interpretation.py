from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re

import httpx
from pydantic import ValidationError

from .i18n import (AVOID_LABELS_EN, CLARIFY_EN, CONSTRAINT_CORRECTIONS_EN, CORRECTION_CHIPS_EN,
                    NEED_LABELS_EN, PLACE_TYPE_LABELS_EN, state_label, ui)
from .schemas import ClarifyOption, CorrectionOptions, InterpretResponse, NeedState, RiskLevel, SelfReport


logger = logging.getLogger("current.interpretation")

# 每次改 SYSTEM_PROMPT 都要抬版本号——留痕靠它才能对得上（FR-30）。
PROMPT_VERSION = "sp2-interpret-v0.7-compact"
INTERPRET_MAX_TOKENS = 420

# 限流和 schema 失败是两回事，重试方式也不一样：
# 429/5xx 是「现在排不上队」，立刻重试等于白试，要等一下；
# schema 失败是「模型说了不合契约的话」，要立刻用 temperature=0 再要一次（FR-26）。
# 智谱免费档限的就是并发，不接这一条的话第一屏会经常悄悄退回规则版。
RATE_LIMIT_ATTEMPTS = 3
RATE_LIMIT_BACKOFF_SECONDS = 1.5


MOOD_RULES: dict[str, tuple[str, ...]] = {
    "quiet": ("安静", "太吵", "不想听", "别说话", "need it quiet", "need quiet", "too loud"),
    "noisy": ("脑子停不下来", "想太多", "一直想", "念头停不下来", "很乱",
              "can't stop thinking", "mind won't stop", "racing thoughts"),
    "spark": ("灵感", "没方向", "想创作", "想看看", "need inspiration", "feel creative", "want inspiration"),
    "tired": ("累坏了", "累死了", "筋疲力尽", "没睡好", "睡不够", "熬夜", "通宵",
              "很累", "好累", "累了", "疲惫", "没精神", "没力气", "困", "累",
              "tired", "exhausted", "wiped out", "drained", "sleepy", "no energy"),
    "empty": ("空落落", "没着落", "空空", "没意思", "feel empty", "feeling empty", "feel hollow", "unanchored"),
    "tight": ("发紧", "紧绷", "绷着", "喘不过", "心慌", "紧张", "不安",
              "tense", "stressed", "wound up", "on edge", "can't breathe"),
    "heated": ("气死我", "气炸了", "想发火", "有股火", "特别生气", "很生气", "火大", "恼火",
               "窝火", "愤怒", "生气", "angry", "furious", "worked up", "want to yell"),
    "near": ("不想一个人待着", "不想自己待着", "不想独处", "想有人", "陪我", "一个人难受", "有人在",
             "want company", "someone nearby", "not be alone"),
    "fresh": ("换个地方", "待腻", "没见过", "出去看看", "change of scene", "somewhere new", "get out of here"),
    "bright": ("特别兴奋", "好兴奋", "很兴奋", "想庆祝", "值得庆祝", "很开心", "挺开心",
               "心情很好", "状态不错", "兴致很好", "太爽了", "开心", "高兴", "快乐", "兴奋", "庆祝",
               "happy", "great mood", "excited", "celebrate"),
    "okay": ("还行", "挺好", "没事", "随便走走", "跳舞", "蹦迪", "想动", "出去嗨", "想玩", "doing okay", "feel okay", "walk around", "go out"),
    "low": ("心情不好", "不开心", "低落", "失落", "沮丧", "难过", "伤心", "难受", "委屈", "想哭", "糟糕",
            "feel low", "feeling low", "sad", "upset", "bad mood", "feel awful"),
}


# 明确的地点 / 活动诉求。它们和情绪向量不是一回事：前者是用户自己说的，
# 后者是系统的推断，所以排序时必须让前者优先。只保存枚举，不保存原句。
PLACE_TYPE_RULES: dict[str, tuple[str, ...]] = {
    "barbecue": ("烤串", "烧烤", "串烧", "撸串", "烤肉", "yakitori", "barbecue", "bbq"),
    "restaurant": ("餐厅", "饭店", "吃饭", "吃点东西", "找吃的", "正餐", "restaurant"),
    "hotpot": ("火锅", "涮肉", "麻辣烫", "hotpot"),
    "dessert": ("甜品", "蛋糕", "冰淇淋", "面包店", "糖水", "dessert"),
    "craft": ("手作", "手工", "陶艺", "做陶", "木工", "编织", "银饰", "craft"),
    "flower": ("插花", "花艺", "花店", "鲜花", "flower"),
    "sports": ("运动馆", "体育馆", "体育中心", "锻炼", "想运动", "运动一下", "work out"),
    "gym": ("健身房", "健身", "fitness center", "gym", "workout"),
    "climbing": ("攀岩", "抱石", "climbing", "bouldering"),
    "swimming": ("游泳", "泳池", "swimming"),
    "badminton": ("羽毛球", "badminton"),
    "basketball": ("篮球", "basketball"),
    "tennis": ("网球", "tennis"),
    "yoga": ("瑜伽", "普拉提", "pilates", "yoga"),
    "music": ("livehouse", "现场音乐", "看演出", "听演出", "听音乐", "音乐现场", "concert"),
    "bar": ("酒吧", "喝一杯", "喝酒", "精酿", "cocktail", "pub"),
    "club": ("夜店", "蹦迪", "跳舞", "club"),
    "karaoke": ("ktv", "KTV", "唱歌", "卡拉ok", "karaoke"),
    "books": ("书店", "看书", "逛书", "bookstore"),
    "records": ("唱片店", "黑胶", "唱片", "records"),
    "cafe": ("咖啡馆", "咖啡店", "喝咖啡", "cafe", "coffee"),
    "tea": ("茶馆", "茶室", "喝茶", "tea house"),
    "park": ("公园", "park"),
    "gallery": ("美术馆", "画廊", "展览", "看展", "gallery"),
    "cinema": ("电影院", "影院", "看电影", "电影资料馆", "cinema"),
    "river": ("河边", "江边", "水边", "湖边", "river", "waterfront"),
    "vintage": ("中古店", "古着", "二手店", "vintage"),
    "lane": ("胡同", "小巷", "街区", "lane", "alley"),
}

PLACE_TYPE_LABELS: dict[str, str] = {
    "barbecue": "吃烤串", "restaurant": "吃顿饭", "hotpot": "吃火锅", "dessert": "吃甜品",
    "craft": "做手作", "flower": "插花", "sports": "运动", "gym": "去健身房", "climbing": "攀岩",
    "swimming": "游泳", "badminton": "打羽毛球", "basketball": "打篮球",
    "tennis": "打网球", "yoga": "做瑜伽或普拉提", "music": "听现场音乐", "bar": "去酒吧",
    "club": "跳舞", "karaoke": "唱歌", "books": "逛书店", "records": "逛唱片店",
    "cafe": "去咖啡馆", "tea": "喝茶", "park": "去公园", "gallery": "看展",
    "cinema": "看电影", "river": "去水边", "vintage": "逛中古店", "lane": "逛街巷",
}

NEED_RULES: dict[str, tuple[str, ...]] = {
    "hide": ("不想见人", "不想被看见", "不被看见", "没人看见我", "想一个人", "自己待着", "躲一躲", "躲",
             "don't want to see anyone", "do not want to see anyone", "want to be alone", "somewhere private"),
    "sit": ("坐一会", "坐很久", "不想动", "sit down", "sit for a while", "don't want to move"),
    "walk": ("走走", "散步", "一直走", "走一会", "take a walk", "keep walking", "go for a walk"),
    "free": ("不花钱", "不想花钱", "不想花很多钱", "没钱", "便宜", "预算低", "少花点", "don't want to spend", "spend nothing", "free", "cheap", "low budget"),
    "green": ("树", "绿色", "公园", "自然", "trees", "greenery", "nature"),
    "new": ("没见过", "新鲜", "换个地方", "something new", "somewhere new", "change of scene"),
    "sound": ("听音乐", "听点声音", "唱片", "listen to music", "hear music", "some sound", "records"),
    "people": ("不想一个人待着", "不想自己待着", "不想独处", "想有人", "陪我", "有人在", "有人就行",
               "生活气", "想聊天", "和人说话", "找人聊", "认识人", "想社交",
               "people around", "someone nearby", "talk to someone", "want company", "socialize"),
    "loud": ("吵一点", "热闹", "蹦迪", "跳舞", "嗨一点", "somewhere loud", "somewhere lively", "party", "go dancing"),
    "slow": ("慢下来", "安静", "缓一缓", "slow down", "take it slow", "somewhere quiet"),
    "hands": ("手上有事", "做点什么", "翻书", "something to do", "keep my hands busy", "browse books"),
    "breathe": ("喘口气", "透气", "发紧", "开阔", "视野", "看远一点", "看夕阳", "夕阳", "吹吹风", "吹风", "微风", "有风",
                "fresh air", "a breeze", "somewhere outside", "catch my breath"),
    "nothing": ("不想决定", "你替我选", "随便", "都可以", "don't want to decide", "you choose", "anything works", "no decisions"),
}

# Safety routing is deliberately rule-first: explicit risk language must never be
# delegated to a model that could miss or downgrade it. Keep self-harm and harm
# to others separate so downstream safety UX can evolve without reclassifying
# historical signals.
URGENT_SELF_HARM_PATTERNS = (
    "不想活", "活不下去", "想死", "结束生命", "结束自己的生命", "轻生", "寻死",
    "自杀", "伤害自己", "杀了自己", "一了百了",
    "want to die", "wanna die", "kill myself", "hurt myself", "harm myself",
    "end my life", "take my own life", "suicidal",
)
URGENT_HARM_TO_OTHERS_PATTERNS = (
    "想杀人", "我要杀", "杀了他", "杀了她", "杀了他们", "杀了她们", "伤害别人",
    "伤害他人", "想砍人", "捅死", "砍死",
    "kill someone", "kill him", "kill her", "kill them", "hurt someone",
    "hurt other people", "harm someone", "harm other people",
)
ELEVATED_PATTERNS = ("撑不住", "失控", "崩溃", "can't go on", "cannot go on")

# Body-level wording only. No clinical or personality labels ever leave this file.
STATE_LABELS: dict[str, str] = {
    "low": "心情有点沉",
    "quiet": "需要安静",
    "noisy": "脑子停不下来",
    "spark": "想要点灵感",
    "tired": "累但静不下来",
    "empty": "空落落的",
    "tight": "心里发紧",
    "heated": "心里有股火",
    "near": "想有人在旁边",
    "fresh": "想换个地方",
    "bright": "心情很明亮",
    "okay": "状态还行",
}

# 「不想要」不能靠给 NEED_LABELS 加个「不」前缀凑出来：
# 「周围有人就行」加个不字会变成「不要周围有人就行」，不像人话。
AVOID_LABELS: dict[str, str] = {
    "people": "想避开人多",
    "loud": "不想吵",
    "sound": "不想听声音",
    "hands": "什么都不想做",
    "new": "不想看新东西",
    "walk": "不想一直走",
    "green": "不想看绿色",
}

NEED_LABELS: dict[str, str] = {
    "hide": "不被人看见",
    "sit": "能坐很久",
    "walk": "能一直走",
    "free": "不用花太多钱",
    "green": "想看见绿色",
    "new": "想看没见过的",
    "sound": "想听点声音",
    "people": "周围有人就行",
    "loud": "想要吵一点",
    "slow": "想慢下来",
    "hands": "想手上有事做",
    "breathe": "想喘口气",
    "nothing": "什么都不想决定",
}

# The six body-feeling chips offered when the user says "不太对" (FR-03 / US-02).
CORRECTION_CHIPS: tuple[tuple[str, str], ...] = (
    ("tight", "心里发紧"),
    ("heated", "心里有股火"),
    ("noisy", "脑子停不下来"),
    ("tired", "累但静不下来"),
    ("empty", "空落落的"),
    ("near", "想有人在旁边"),
    ("fresh", "想换个地方"),
    ("quiet", "需要安静"),
    ("low", "心情有点沉"),
    ("bright", "心情很明亮"),
)

# 诉求这一环：按「空间 / 刺激 / 恢复」各挑最常被说错的，凑够但不超过 6 个。
NEED_CORRECTIONS: tuple[str, ...] = ("hide", "sit", "walk", "green", "people", "slow", "new", "free")

# 约束这一环：key 用 "字段:值" 编码，前端照着改 NeedState，服务端仍会按
# NeedState 的字面量重新校验一次，客户端塞不进白名单以外的值。
CONSTRAINT_CORRECTIONS: tuple[tuple[str, str], ...] = (
    ("max_travel_minutes:15", "太远了，就近"),
    ("budget_level:free", "不想花钱"),
    ("environment:indoor", "想待在室内"),
    ("environment:outdoor", "想在户外"),
    ("social_mode:alone", "想一个人"),
    ("social_mode:with_people", "想周围有人"),
)

CLARIFY_QUESTIONS: dict[str, tuple[str, tuple[tuple[str, str], ...]]] = {
    "social_mode": (
        "只问一句：现在想要哪种陪伴感？",
        (("alone", "想一个人"), ("low_contact", "有人但不说话"),
         ("with_people", "热闹，能和人说话"), ("either", "都行")),
    ),
    "max_travel_minutes": (
        "只问一句：现在最多愿意在路上花多久？",
        (("10", "10 分钟内"), ("25", "20 分钟左右"), ("60", "远一点也行")),
    ),
    "budget_level": (
        "只问一句：今天想不想花钱？",
        (("free", "不想花钱"), ("low", "花一点可以"), ("unknown", "都行")),
    ),
}


# 「不想要」在中文里几乎总是明说的，规则也接得住——模型没跑的时候
# （没配 Key、契约失败）不能连这个都丢。词表和 need_keys 是同一套。
AVOID_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("people", ("不想见人", "不想见到人", "别跟人说话", "不想说话", "不想社交",
                "人少点", "人少的", "少点人", "没什么人", "不要太多人", "别太多人", "不想应付",
                "don't want to see anyone", "do not want to see anyone", "avoid people", "fewer people", "not crowded",
                "don't want to socialize", "do not want to socialize")),
    ("loud", ("不想去太吵", "不想太吵", "不想吵", "别太吵", "不要太吵", "太吵了", "怕吵", "安静点", "不要吵",
              "not loud", "too loud", "avoid noise", "somewhere quiet")),
    ("hands", ("什么都不做", "啥都不想做", "不想动手", "不想干活", "不用动脑", "do nothing", "nothing to do")),
)


def _token_pattern(token: str) -> re.Pattern[str]:
    """Compile Latin tokens as words while keeping Chinese substring behaviour."""
    escaped = re.escape(token)
    if token.isascii() and re.search(r"[A-Za-z0-9]", token):
        escaped = rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])"
    return re.compile(escaped, flags=re.IGNORECASE)


def _token_match(text: str, token: str) -> re.Match[str] | None:
    return _token_pattern(token).search(text)


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(_token_match(text, item) for item in patterns)


_NEGATED_PREFIX = re.compile(
    r"(?:并不想|并不愿|不想|不愿|不要|没想|没有|不是|并不|并没有|谈不上|算不上|不|没)"
    r"[^，。！？,.!?；;]{0,3}$|"
    r"(?:\b(?:do not|don't|doesn't|didn't|can't|cannot|won't|wouldn't|shouldn't|not|never|no)\b)"
    r"(?:\s+[A-Za-z'-]+){0,4}\s*$",
    flags=re.IGNORECASE,
)


def _affirmed_matches(text: str, patterns: tuple[str, ...]) -> list[tuple[int, str]]:
    """Return longest, non-overlapping mentions that are not negated.

    Substring counting made ``不难过`` count as low and let ``开心`` inside
    ``不开心`` compete with the negative phrase. Mood words need a little
    scope awareness; explicit request phrases keep their separate rules.
    """
    spans: list[tuple[int, int, str]] = []
    for token in sorted(patterns, key=len, reverse=True):
        for match in _token_pattern(token).finditer(text):
            index, end = match.span()
            prefix = text[max(0, index - 48):index]
            folded_token = token.casefold()
            token_is_negative_phrase = token.startswith(("不", "没", "别", "无")) or folded_token.startswith(
                ("don't", "do not", "not ", "no ", "never ")
            )
            overlaps = any(index < used_end and end > used_start for used_start, used_end, _ in spans)
            if not overlaps and (token_is_negative_phrase or not _NEGATED_PREFIX.search(prefix)):
                spans.append((index, end, match.group(0)))
    return sorted(((start, token) for start, _end, token in spans), key=lambda item: item[0])


def _mood_matches(text: str) -> dict[str, list[tuple[int, str]]]:
    return {mood: _affirmed_matches(text, tokens) for mood, tokens in MOOD_RULES.items()}


def _last_pattern_position(text: str, patterns: tuple[str, ...]) -> int:
    matches = _affirmed_matches(text, patterns)
    return matches[-1][0] if matches else -1


def interpret_with_rules(text: str) -> InterpretResponse:
    mood_matches = _mood_matches(text)
    mood_scores = {mood: len(matches) for mood, matches in mood_matches.items()}
    # 「难过 + 想找个安静的地方」里，难过是状态，安静是要求；不能因为词表
    # 顺序把要求反过来当成情绪。多个明确感受同时出现时，同分取后说的那一个，
    # 才能读懂「虽然很累，但现在特别高兴」这类转折句。
    felt_moods = ("low", "bright", "tired", "empty", "tight", "heated")
    candidates = felt_moods if any(mood_scores[mood] for mood in felt_moods) else tuple(MOOD_RULES)
    mood_id = max(
        candidates,
        key=lambda mood: (mood_scores[mood], mood_matches[mood][-1][0] if mood_matches[mood] else -1),
    )
    if mood_scores[mood_id] == 0:
        # 没提情绪，不等于低落。后面的复述会按低置信度明确说“不硬猜”。
        mood_id = "okay"

    not_alone = _contains_any(
        text,
        ("不想一个人待着", "不想一个人", "不想自己待着", "不想独处",
         "don't want to be alone", "do not want to be alone", "not be alone"),
    )
    needs = [key for key, tokens in NEED_RULES.items() if _affirmed_matches(text, tokens)]
    folded = text.casefold()
    place_types = [
        key for key, tokens in PLACE_TYPE_RULES.items()
        if _affirmed_matches(folded, tuple(token.casefold() for token in tokens))
    ]
    risk_text = text.casefold()
    self_harm = _contains_any(risk_text, URGENT_SELF_HARM_PATTERNS)
    harm_to_others = _contains_any(risk_text, URGENT_HARM_TO_OTHERS_PATTERNS)
    urgent = self_harm or harm_to_others
    elevated = not urgent and _contains_any(risk_text, ELEVATED_PATTERNS)
    risk_level = RiskLevel.urgent if urgent else RiskLevel.elevated if elevated else RiskLevel.ordinary

    risk_signals: list[str] = []
    if self_harm:
        risk_signals.append("explicit_self_harm_language")
    if harm_to_others:
        risk_signals.append("explicit_harm_to_others_language")
    if elevated:
        risk_signals.append("severe_distress_language")

    low_energy = ("没力气", "筋疲力尽", "很累", "好累", "累坏了", "累死了", "动不了", "不想动",
                  "no energy", "tired", "exhausted", "wiped out", "drained", "don't want to move")
    high_energy = ("有力气", "想运动", "想跳", "想跑", "跳舞", "蹦迪", "想动", "出去嗨",
                   "work out", "workout", "go running", "go dancing", "want to move")
    activated = ("特别兴奋", "好兴奋", "很兴奋", "兴奋", "激动", "坐不住",
                 "very excited", "so excited", "excited", "thrilled", "can't sit still")
    low_at = _last_pattern_position(text, low_energy)
    high_at = _last_pattern_position(text, high_energy)
    activated_at = _last_pattern_position(text, activated)
    energy = 2
    if max(high_at, activated_at) > low_at:
        energy = 4 if high_at >= activated_at else 3
    elif low_at >= 0:
        energy = 1

    budget = "free" if _contains_any(
        text, ("不花钱", "不想花钱", "没钱", "免费", "spend nothing", "don't want to spend", "free")
    ) else "low" if _contains_any(
        text, ("便宜", "不想花很多钱", "预算低", "少花点", "cheap", "low budget", "not spend much")
    ) else "unknown"
    wants_interaction = bool(_affirmed_matches(
        text,
        ("热闹", "很闹", "想聊天", "和人说话", "找人聊", "认识人", "想社交",
         "talk to someone", "meet people", "socialize", "somewhere lively"),
    ))
    wants_company = not_alone or bool(_affirmed_matches(
        text,
        ("想有人", "陪我", "有人但不说话", "不用说话", "有人就行", "有人在旁边",
         "want company", "people nearby but no talking", "company without talking"),
    ))
    wants_alone = bool(_affirmed_matches(
        text,
        ("不想见人", "想一个人", "自己待着", "别跟人说话",
         "don't want to see anyone", "do not want to see anyone", "want to be alone", "avoid people"),
    )) and not not_alone
    social = "with_people" if wants_interaction else "low_contact" if wants_company else "alone" if wants_alone else "either"
    explicitly_outdoor = _contains_any(
        text, ("不想待在室内", "不要室内", "don't want to stay inside", "not indoors")
    )
    explicitly_indoor = _contains_any(
        text, ("不要户外", "不想在外面", "not outside", "don't want to be outside")
    )
    wants_outdoor = bool(_affirmed_matches(text, (
        "想去户外", "想在户外", "想去外面", "露天", "晒太阳", "开阔视野", "视野开阔",
        "看远一点", "看夕阳", "夕阳", "能吹风", "吹吹风", "吹风", "微风", "有风",
        "河边", "江边", "水边", "湖边", "outside", "outdoors", "fresh air", "a breeze",
        "by the river", "by the water", "in the sun",
    )))
    wants_indoor = bool(_affirmed_matches(
        text, ("想待在室内", "想去室内", "indoors", "stay inside")
    ))
    environment = (
        "outdoor" if explicitly_outdoor or (wants_outdoor and not explicitly_indoor)
        else "indoor" if explicitly_indoor or wants_indoor
        else "either"
    )

    # 同一个词表两边都出现时，「想要」压过「不想要」：用户刚说了想要它。
    avoid = [key for key, tokens in AVOID_RULES if _contains_any(text, tokens) and key not in needs]

    state = NeedState(
        mood_id=mood_id,
        need_keys=needs[:6],
        place_types=place_types[:3],
        avoid_tags=avoid[:8],
        energy=energy,
        social_mode=social,
        budget_level=budget,
        environment=environment,
        confidence=0.58 if mood_scores[mood_id] else 0.35,
        risk_level=risk_level,
        risk_signals=risk_signals,
    )
    return InterpretResponse(
        state=state,
        acknowledgement="我听见了。先不逼你解释清楚，我按你刚刚说的替你缩小范围。",
        source="rules",
    )


def _matched_tokens(text: str, patterns: tuple[str, ...]) -> list[str]:
    """Return the exact text the user typed, even for case-insensitive English matches."""
    return [token for _position, token in _affirmed_matches(text, patterns)]


def _evidence_for(text: str, state: NeedState, lang: str = "zh") -> list[str]:
    """Quote the user's own words back. Never inferred, never stored, never logged.

    同一句话只引用一次。之前「不想见人」会先作为诉求出现、再作为社交约束出现，
    同一个信号说两遍，看起来像没读懂。
    """
    evidence: list[str] = []
    cited: set[str] = set()
    english = lang == "en"

    for _position, token in _affirmed_matches(text, MOOD_RULES.get(state.mood_id, ())):
        evidence.append(f"You said 「{token}」" if english else f"你说了「{token}」")
        cited.add(token.casefold())
        break

    # 具体行动比抽象情绪更接近用户真正要求的东西，必须原样指出它是排序依据。
    for key in state.place_types:
        tokens = [t for t in _matched_tokens(text, PLACE_TYPE_RULES.get(key, ())) if t.casefold() not in cited]
        if not tokens:
            continue
        evidence.append(f"「{tokens[0]}」 — I’ll start there" if english else f"「{tokens[0]}」——我先按这个找")
        cited.add(tokens[0].casefold())
        if len(evidence) >= 3:
            break

    for key in state.need_keys:
        tokens = [t for t in _matched_tokens(text, NEED_RULES.get(key, ())) if t.casefold() not in cited]
        if not tokens:
            continue
        label = NEED_LABELS_EN.get(key, key) if english else NEED_LABELS.get(key, key)
        evidence.append(f"「{tokens[0]}」 — I kept that in the search" if english else f"「{tokens[0]}」——我理解成{label}")
        cited.add(tokens[0].casefold())
        if len(evidence) >= 2:
            break

    if len(evidence) < 3:
        # 兜底那条也必须引用用户真说过的词，不能写死一句「你说了不想见人」。
        constraints: list[tuple[bool, tuple[str, ...], str, str]] = [
            (state.budget_level in {"free", "low"}, ("不花钱", "不想花钱", "不想花很多钱", "没钱", "免费", "便宜", "预算低", "少花点", "spend nothing", "don't want to spend", "free", "cheap", "low budget"), "所以我只找花不了什么钱的地方", "so I’ll keep the cost low"),
            (state.social_mode == "alone", ("不想见人", "一个人", "别跟人说话", "躲", "don't want to see anyone", "do not want to see anyone", "want to be alone", "avoid people"), "所以我把人多的地方去掉了", "so I’ll leave crowded places out"),
            ("people" in state.avoid_tags, ("不想见人", "不想见到人", "人少点", "人少的", "少点人", "没什么人", "不要太多人", "别太多人", "fewer people", "not crowded", "avoid people"), "所以我把人多的地方往后放了", "so crowded places will move down"),
            (state.energy <= 1, ("没力气", "很累", "好累", "累坏了", "累死了", "动不了", "不想动", "困", "疲惫", "no energy", "tired", "exhausted", "wiped out", "drained"), "所以我把远的地方往后放了", "so I’ll keep the trip short"),
        ]
        for applies, tokens, consequence, consequence_en in constraints:
            if not applies:
                continue
            fresh = [t for t in _matched_tokens(text, tokens) if t.casefold() not in cited]
            if not fresh:
                continue
            evidence.append(f"「{fresh[0]}」 — {consequence_en}" if english else f"「{fresh[0]}」——{consequence}")
            cited.add(fresh[0].casefold())
            break

    if not evidence:
        evidence.append("I couldn’t find a clear signal in that, so I’m not fully sure." if english
                        else "你说的话里我没抓到很明确的线索，所以这一条我不太确定")
    return evidence[:3]


def _already_holds(state: NeedState, encoded: str) -> bool:
    """已经是这个约束了就别再当成「纠错选项」摆出来。"""
    field, _, raw = encoded.partition(":")
    current = getattr(state, field, None)
    if field == "max_travel_minutes":
        return current is not None and current <= int(raw)
    return str(current) == raw


def _needs_clarification(state: NeedState) -> str | None:
    """Ask at most one question, and only when the answer changes the shortlist."""
    if state.place_types:
        # 用户已经明确说了去哪类地方 / 做什么，就先给结果，别把他拉回抽象选择题。
        return None
    concrete_constraints = len(state.need_keys) + len(state.avoid_tags) + int(state.environment != "either")
    if concrete_constraints >= 2:
        # 「人少 + 能吹风」已经足够排序。再追问陪伴感或路程，会把一次自然表达
        # 拆回问卷，也违背“一次最多问一个、只有必要时才问”的约束。
        return None
    if state.social_mode == "either" and len(state.need_keys) < 2:
        return "social_mode"
    if state.energy <= 1 and state.max_travel_minutes is None:
        return "max_travel_minutes"
    if state.budget_level == "unknown" and "free" not in state.need_keys and state.confidence < 0.5:
        return "budget_level"
    return None


def _restatement(state: NeedState, lang: str = "zh") -> str:
    if state.place_types:
        labels = (PLACE_TYPE_LABELS_EN if lang == "en" else PLACE_TYPE_LABELS)
        named = [labels[key] for key in state.place_types if key in labels][:2]
        if lang == "en":
            return "I hear you. You were clear about what you want: " + " and ".join(named) + ". I’ll start there."
        empathy = {
            "low": "听起来今天有点不好受。", "tight": "听起来你现在还绷着。",
            "heated": "听起来你现在心里有股火。",
            "tired": "听起来你真的累了。", "empty": "听起来心里有点空。",
            "bright": "听起来你现在兴致不错。",
        }.get(state.mood_id, "")
        return empathy + "你说得很具体：" + "、".join(named) + "。我先按这个找，不把它换成别的。"
    if lang == "en":
        label = state_label(state.mood_id, "en") or "hard to name"
        needs = [NEED_LABELS_EN[key] for key in state.need_keys if key in NEED_LABELS_EN][:2]
        if needs:
            return ui("restate_with_need", "en", label=label, needs=" and ".join(needs)) or ""
        return ui("restate", "en", label=label) or ""
    if state.confidence < 0.45:
        return "我还没听准你的状态，先不硬猜。只问一个会改变推荐的问题。"
    label = STATE_LABELS.get(state.mood_id, "说不太清楚")
    needs = [NEED_LABELS[key] for key in state.need_keys if key in NEED_LABELS][:2]
    tail = "，需要一个" + "、".join(needs) + "的地方" if needs else ""
    empathy = {
        "low": "听起来今天有点不好受。", "tight": "听起来你现在还绷着。",
        "heated": "听起来你现在心里有股火。",
        "tired": "听起来你真的累了。", "empty": "听起来心里有点空。",
        "bright": "听起来你现在兴致不错。",
    }.get(state.mood_id, "我听见了。")
    return f"{empathy}我理解你更接近「{label}」{tail}。不对的话，我马上换。"


# 模型会把 prompt 里的字段名、占位符原样吐给用户。这些一出现就整条丢掉。
EVIDENCE_LEAKS = ("mood_id", "need_keys", "social_mode", "budget_level", "risk_level",
                  "所以我怎么理解", "json", "字段", "对应")


def _quotes_the_user(line: str, text: str) -> bool:
    """证据必须引用用户真说过的词，而且得是小在的口气。

    模型编一句听起来很懂的话是很容易的，所以逐条核对「」里的片段确实出现在
    原文里；再挡掉泄漏出来的字段名和过长的书面语（FR-28 代码侧护栏）。
    """
    # Chinese evidence is compact; natural English needs a word limit instead
    # of the Chinese character limit or nearly every honest line is discarded.
    has_cjk = bool(re.search(r"[\u3400-\u9fff]", line.replace("「", "").replace("」", "")))
    too_long = len(line) > 40 if has_cjk else len(line.split()) > 25
    if too_long or any(leak in line.lower() for leak in EVIDENCE_LEAKS):
        return False
    quoted = re.findall(r"「([^」]{1,60})」", line)
    return bool(quoted) and all(q.casefold() in text.casefold() for q in quoted)


def _decorate(response: InterpretResponse, text: str, *, model_evidence: list[str] | None = None, lang: str = "zh") -> InterpretResponse:
    state = response.state
    # These controls are filled by the user after interpretation, never by the LLM.
    state.self_report = SelfReport()
    # 代码侧护栏：avoid_tags 现在真的会压分，所以它必须和 need_keys 用同一套词表，
    # 且不能自相矛盾。模型编出来的词直接丢掉，两边都出现时「想要」压过「不想要」。
    state.avoid_tags = [
        key for key in dict.fromkeys(state.avoid_tags)
        if key in NEED_LABELS and key not in state.need_keys
    ][:8]
    response.state_label = state_label(state.mood_id, lang) or STATE_LABELS.get(state.mood_id, "说不太清楚")
    response.acknowledgement = _restatement(state, lang)

    # 模型读懂了、规则没读懂的句子，证据也得跟着模型走——
    # 否则会出现「我猜你心里发紧」配「我没抓到明确线索」这种自相矛盾。
    verified: list[str] = []
    if model_evidence:
        verified = [
            line.strip() for line in model_evidence
            if isinstance(line, str) and line.strip() and _quotes_the_user(line, text)
        ][:3]
    response.evidence = verified or _evidence_for(text, state, lang)
    # FR-03：四环都要能一步纠正，不能只让用户改「状态」这一环。
    # 地点那一环不给选项——「这几个都不想去」本身就是动作。
    english = lang == "en"
    chips = CORRECTION_CHIPS_EN if english else CORRECTION_CHIPS
    constraints = CONSTRAINT_CORRECTIONS_EN if english else CONSTRAINT_CORRECTIONS
    need_labels = NEED_LABELS_EN if english else NEED_LABELS
    response.corrections = CorrectionOptions(
        state=[
            ClarifyOption(key=key, label=label)
            for key, label in chips
            if key != state.mood_id
        ][:6],
        need=[
            ClarifyOption(key=key, label=need_labels[key])
            for key in NEED_CORRECTIONS
            if key not in state.need_keys and key in need_labels
        ][:6],
        constraint=[
            ClarifyOption(key=key, label=label)
            for key, label in constraints
            if not _already_holds(state, key)
        ][:6],
    )

    clarify_table = CLARIFY_EN if lang == "en" else CLARIFY_QUESTIONS
    field = None if state.risk_level is not RiskLevel.ordinary else _needs_clarification(state)
    if field and field in clarify_table:
        question, options = clarify_table[field]
        state.needs_clarification = True
        state.clarifying_question = question
        response.clarify_field = field
        response.clarify_options = [ClarifyOption(key=key, label=label) for key, label in options]
    else:
        state.needs_clarification = False
        state.clarifying_question = None
    return response


SYSTEM_PROMPT = """你是 Current 的需求解释器。把用户原话转换成 JSON；不诊断、不贴人格标签、不补写用户没说的事实。
只输出以下结构：
{
  "mood_id": "low|quiet|noisy|spark|tired|empty|tight|heated|near|fresh|bright|okay",
  "need_keys": ["hide|sit|walk|free|green|new|sound|people|loud|slow|hands|breathe|nothing"],
  "place_types": ["barbecue|restaurant|hotpot|dessert|craft|flower|sports|gym|climbing|swimming|badminton|basketball|tennis|yoga|music|bar|club|karaoke|books|records|cafe|tea|park|gallery|cinema|river|vintage|lane"],
  "energy": 0-4,
  "social_mode": "alone|low_contact|with_people|either",
  "time_minutes": 10-720 或 null,
  "max_travel_minutes": 5-180 或 null,
  "budget_level": "free|low|medium|high|unknown",
  "environment": "indoor|outdoor|either",
  "avoid_tags": ["同 need_keys 枚举，只放用户明确不要的"],
  "confidence": 0-1,
  "needs_clarification": boolean,
  "clarifying_question": string 或 null,
  "risk_level": "ordinary|elevated|urgent",
  "risk_signals": [],
  "evidence": ["1-3 条用户可见短句"]
}
规则：
1. 直接表达 > 场景推断；转折后最后强调的状态优先。证据不足用 okay 且低 confidence。
2. tired 只用于明确“累/困/没睡好/没力气”；加班、开会、很晚不能单独证明累。
3. bright 是开心/兴奋/庆祝；noisy 是念头反复，二者不能混。负面不等于想安静，正面不等于想休息。
4. need_keys=想要；avoid_tags=明确不要；同一词不能同时出现。“不想见人”→avoid people，“不想吵”→avoid loud。
5. place_types 只放用户明说的地点/活动，绝不能从情绪猜或换掉。例：难过但想吃烤串→mood_id=low, place_types=["barbecue"]。
6. “不想一个人但也不想说话”→near + people + low_contact；不能变成 alone/hide。
7. 只有缺失信息会改变推荐时才问一个问题。
8. evidence 每条≤25字，必须用「」逐字引用用户原话；短、白话、无字段名/术语/临床词。例：「谁都不想理」——所以我把人多的去掉了。"""


ENGLISH_SUFFIX = """

IMPORTANT — this user reads English. Write `evidence` and `clarifying_question` in English.
Everything else (the enum values) stays exactly as specified above.
Same voice in English: short, plain, physical. Not clinical, not flowery.
Quote the user's own words inside 「」 exactly as they typed them, even if they typed Chinese.
Good: 「had a fight」 — so I'm guessing you're still braced for something
Bad: The user is experiencing interpersonal conflict-related distress"""


def _extract_json(content: str) -> dict:
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
    return json.loads(content)


def _digest(text: str) -> str:
    """留痕只留摘要。原话不进日志——哈希能对上同一句话，但还原不出来（FR-30）。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _trace(*, outcome: str, text: str, attempt: int, model: str, detail: str = "") -> None:
    logger.info(
        json.dumps(
            {
                "event": "interpretation",
                "prompt_version": PROMPT_VERSION,
                "model": model,
                "attempt": attempt,
                "input_digest": _digest(text),
                "input_length": len(text),
                "outcome": outcome,
                "detail": detail,
            },
            ensure_ascii=False,
        )
    )


async def _call_model(client: httpx.AsyncClient, *, base_url: str, api_key: str, model: str, text: str, temperature: float, lang: str = "zh") -> tuple[NeedState, list[str] | None]:
    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": INTERPRET_MAX_TOKENS,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT + (ENGLISH_SUFFIX if lang == "en" else "")},
            {"role": "user", "content": text},
        ],
    }
    # Qwen3 系列默认开思考链。我们这一步是受约束的信息抽取，不需要它推理，
    # 开着会从 5 秒变成 18 秒——直接吃掉 PRD §8 给的 3 秒预算。
    # 这个参数是 Qwen 专有的，别的厂商会拒收，所以按模型名判断。
    if "qwen3" in model.lower():
        payload["enable_thinking"] = False
    response = await client.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
    )
    response.raise_for_status()
    payload = _extract_json(response.json()["choices"][0]["message"]["content"])
    evidence = payload.pop("evidence", None)
    return NeedState.model_validate(payload), evidence


def _is_transient(error: Exception) -> bool:
    """值得等一下再试的：排队、服务端抖动、连接被重置。

    模型提供商说「你参数不对」不在此列——那种重试多少次都是一样的答案。
    """
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in (429, 500, 502, 503, 504)
    return isinstance(error, httpx.TransportError)


async def _call_model_with_backoff(client, *, base_url, api_key, model, text, temperature, attempt, lang="zh"):
    """排队排不上就等一下再要一次。等不到就把异常抛出去，走上面的契约兜底。"""
    last: Exception | None = None
    for round_index in range(RATE_LIMIT_ATTEMPTS):
        try:
            return await _call_model(client, base_url=base_url, api_key=api_key, model=model, text=text, temperature=temperature, lang=lang)
        except Exception as error:  # noqa: BLE001 - 分流后原样抛出
            if not _is_transient(error):
                raise
            last = error
            _trace(outcome="transient_retry", text=text, attempt=attempt, model=model,
                   detail=f"{type(error).__name__} round {round_index + 1}/{RATE_LIMIT_ATTEMPTS}")
            if round_index + 1 < RATE_LIMIT_ATTEMPTS:
                await asyncio.sleep(RATE_LIMIT_BACKOFF_SECONDS * (round_index + 1))
    raise last  # type: ignore[misc]


async def interpret(text: str, lang: str = "zh") -> InterpretResponse:
    rule_result = interpret_with_rules(text)
    # Explicit high-risk language is never delegated to a generative model.
    if rule_result.state.risk_level == RiskLevel.urgent:
        _trace(outcome="rules_safety_short_circuit", text=text, attempt=0, model="none")
        return _decorate(rule_result, text, lang=lang)

    api_key = os.getenv("LLM_API_KEY") or os.getenv("api_key")
    if not api_key:
        _trace(outcome="rules_no_model_configured", text=text, attempt=0, model="none")
        return _decorate(rule_result, text, lang=lang)

    base_url = (os.getenv("LLM_BASE_URL") or os.getenv("base_url") or "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("LLM_MODEL") or os.getenv("model") or "glm-4.7-flash"

    # 输出契约（FR-26）：校验失败以 temperature=0 重试一次，再失败走规则兜底，绝不空屏。
    async with httpx.AsyncClient(timeout=20) as client:
        for attempt, temperature in enumerate((0.1, 0.0), start=1):
            try:
                state, model_evidence = await _call_model_with_backoff(
                    client, base_url=base_url, api_key=api_key, model=model, text=text,
                    temperature=temperature, attempt=attempt, lang=lang,
                )
            except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError, ValidationError) as error:
                _trace(outcome="contract_failed", text=text, attempt=attempt, model=model, detail=type(error).__name__)
                continue

            # 代码侧护栏：模型不能把规则已经认定的风险降级（FR-28）。
            if rule_result.state.risk_level == RiskLevel.elevated and state.risk_level == RiskLevel.ordinary:
                state.risk_level = RiskLevel.elevated
                state.risk_signals = rule_result.state.risk_signals
            # 用户明确说出的词比模型推断更硬。模型即使漏了「烤串 / 手作 / 想聊天」，
            # 代码也会把规则识别到的信号补回去，不让生产模型把具体诉求抽象掉。
            state.place_types = list(dict.fromkeys(rule_result.state.place_types + state.place_types))[:3]
            state.need_keys = list(dict.fromkeys(rule_result.state.need_keys + state.need_keys))[:6]
            state.avoid_tags = list(dict.fromkeys(rule_result.state.avoid_tags + state.avoid_tags))[:8]
            if rule_result.state.social_mode != "either":
                state.social_mode = rule_result.state.social_mode
            if rule_result.state.environment != "either":
                state.environment = rule_result.state.environment
            if rule_result.state.energy != 2:
                state.energy = rule_result.state.energy
            if rule_result.state.budget_level != "unknown":
                state.budget_level = rule_result.state.budget_level
            explicit_moods = _mood_matches(text)
            if any(explicit_moods.values()):
                state.mood_id = rule_result.state.mood_id
            elif state.mood_id == "tired":
                # “加班 / 开会 / 很晚”不等于身体疲惫。生产模型一旦把含糊场景
                # 统一归到 tired，整个推荐就会塌成安静休息。没有明确疲劳证据时
                # 宁可承认没听准，也不替用户制造一个状态。
                state.mood_id = "okay"
                state.confidence = min(state.confidence, 0.4)
                model_evidence = None
            _trace(outcome="model_ok", text=text, attempt=attempt, model=model)
            return _decorate(
                InterpretResponse(
                    state=state,
                    acknowledgement="我听见了。先不逼你解释清楚，我按你刚刚说的替你缩小范围。",
                    source="model",
                ),
                text,
                model_evidence=model_evidence,
                lang=lang,
            )

    _trace(outcome="rules_fallback_after_retry", text=text, attempt=2, model=model)
    return _decorate(rule_result, text, lang=lang)
