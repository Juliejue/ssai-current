"""现场从地图上找地点（FR-16 的前半段）。

在这之前，候选集是 `data/places.json` 里人工整理的 26 个北京地点。
排序逻辑是真的，AI 理解也是真的，但它们排的是一份写死的清单——
用户在北京以外、或者说了一个我们没预设的场景，拿到的还是那 26 个里的一个。

这个模块补的就是这一环：拿用户此刻的位置去高德周边搜索，
把搜回来的 POI 变成和人工地点同一个形状，交给同一套打分逻辑排序。

两类地点**故意不平权**，因为它们的可信度不一样：

| | 人工核对过的 26 个 | 现场搜出来的 |
|---|---|---|
| 身份 | 人一个个核对过 | 高德自己的 POI 记录 |
| 导航 | 给 | 给（坐标就是这个 POI 自己的） |
| 围栏在场证明 | 给 | **不给**——它不进任何汇总，也就不需要防作弊 |
| 「小在眼中的这里」 | 人写的 | 没有，不编 |
| 匿名汇总 | 攒够 5 条才出现 | 永远没有 |

界面上必须看得出这是哪一类。把搜索结果说成是我们核对过的，
是这个产品里最不能犯的错。
"""

from __future__ import annotations

import asyncio
import re
import time
from itertools import zip_longest
from typing import Any

from .map_provider import AmapClient, MapProviderError
from .schemas import Location, NeedState


# 分组搜，而不是一次把所有类型丢进去。
# 高德按距离排序、一次只给 25 条——在国贸这种地方，最近的 25 个 POI 全是咖啡店，
# 结果就是「附近没有公园」。每组各搜各的，每组都能拿到自己那一类里最近的几个。
# 另外：请求用 typecode，但**分类看返回的 type 字符串**，因为高德的 typecode
# 并不严谨（要 140300 美术馆会返回会展中心）。
# 用关键词搜，不用分类编码。
#
# 试过分类编码，那条路走不通：高德的类目是给「找一家店」用的，不是给
# 「找一个能待着的地方」用的。要 110204 纪念馆会给你陈独秀旧居和劳动人民文化宫，
# 要 061201 会把中古店和典当行混在一起。类目对了，气质全错。
#
# 关键词是我们能控制气质的地方。这份词表对着的是真实需求——
# Threads 上那些「北京到底有啥可以安静呆着的地方」「喝咖啡喝酒看书听歌买唱片之地」
# 的帖子，底下被反复点名的就是这些东西。
#
# 而且关键词跟着此刻的状态变：想动手的人搜到的和想发呆的人搜到的，本来就不该一样。
KEYWORD_PROFILES: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...]], ...] = (
    # 关键词,    类别,       这些 need_keys 会点亮它,        这些 mood 会点亮它
    ("书店",     "books",    ("hide", "sit", "slow", "nothing"), ("quiet", "tired", "low", "noisy")),
    ("咖啡",      "cafe",     ("sit", "slow", "hands"),          ("tired", "empty", "okay", "near")),
    ("公园",      "park",     ("walk", "green", "breathe"),      ("tight", "heated", "noisy", "fresh", "okay")),
    ("美术馆",     "gallery",  ("new", "slow", "hide"),           ("spark", "fresh", "empty")),
    ("画廊",      "gallery",  ("new",),                          ("spark", "fresh")),
    ("茶室",      "tea",      ("sit", "slow", "breathe"),        ("tight", "tired", "quiet")),
    ("黑胶",      "records",  ("sound", "hands", "new"),         ("spark", "fresh", "low")),
    ("中古店",     "vintage",  ("new", "hands"),                  ("spark", "fresh")),
    ("陶艺",      "craft",    ("hands",),                        ("spark", "empty")),
    ("花艺",      "flower",   ("hands", "green"),                ("low", "empty", "near")),
    ("运动馆",     "sports",   ("hands", "loud"),                 ("bright", "heated", "okay", "fresh")),
    ("livehouse", "music",    ("sound", "people", "loud"),       ("spark", "empty", "near")),
    ("剧场",      "cinema",   ("hide", "nothing"),               ("noisy", "tired")),
    ("电影院",     "cinema",   ("hide", "nothing"),               ("noisy", "tired", "low")),
    ("河",        "river",    ("walk", "green", "breathe"),      ("tight", "heated", "noisy", "fresh")),
    ("胡同",      "lane",     ("walk", "new"),                   ("fresh", "okay", "spark")),
    ("文创园",     "lane",     ("walk", "new"),                   ("fresh", "spark")),
)

# 用户点名活动时先搜这一组。一个类型最多两个关键词，既提高召回，也不让
# 六次跨境请求全耗在同一种叫法上。
PLACE_TYPE_SEARCHES: dict[str, tuple[tuple[str, str], ...]] = {
    "barbecue": (("烧烤", "barbecue"), ("烤串", "barbecue")),
    "restaurant": (("餐厅", "restaurant"),),
    "hotpot": (("火锅", "hotpot"),),
    "dessert": (("甜品", "dessert"),),
    "craft": (("手作", "craft"), ("陶艺", "craft")),
    "flower": (("花艺", "flower"), ("插花", "flower")),
    "sports": (("体育中心", "sports"), ("健身房", "sports")),
    "climbing": (("攀岩馆", "climbing"),),
    "swimming": (("游泳馆", "swimming"),),
    "badminton": (("羽毛球馆", "badminton"),),
    "basketball": (("篮球馆", "basketball"), ("篮球场", "basketball")),
    "tennis": (("网球场", "tennis"),),
    "yoga": (("瑜伽馆", "yoga"), ("普拉提", "yoga")),
    "music": (("livehouse", "music"),),
    "bar": (("酒吧", "bar"),),
    "club": (("夜店", "club"),),
    "karaoke": (("KTV", "karaoke"),),
    "books": (("书店", "books"),),
    "records": (("黑胶", "records"),),
    "cafe": (("咖啡", "cafe"),),
    "tea": (("茶室", "tea"),),
    "park": (("公园", "park"),),
    "gallery": (("美术馆", "gallery"),),
    "cinema": (("电影院", "cinema"),),
    "river": (("河", "river"),),
    "vintage": (("中古店", "vintage"),),
    "lane": (("胡同", "lane"),),
}

# 不管什么状态都先搜这几个：它们是这份需求里最通用的三样。
BASELINE_KEYWORDS = ("书店", "咖啡", "公园")

# 一次最多发几个关键词请求。每个都是一次跨境往返，多了就慢。
MAX_KEYWORD_SEARCHES = 6

# 搜多远。太小了在郊区搜不到东西，太大了会推荐到跨城的地方。
DISCOVERY_RADIUS_M = 5000
DISCOVERY_PAGE_SIZE = 10


def keywords_for(state: NeedState) -> list[str]:
    """按此刻的状态挑关键词。同一个人说「想动手」和说「想发呆」，搜的词不一样。"""
    needs = set(state.need_keys)
    avoided = set(state.avoid_tags)
    chosen: list[str] = []
    for place_type in state.place_types:
        for keyword, _category in PLACE_TYPE_SEARCHES.get(place_type, ()):
            if keyword not in chosen:
                chosen.append(keyword)
    scored: list[tuple[int, str]] = []
    for keyword, _category, need_keys, moods in KEYWORD_PROFILES:
        # 用户明说不想要的，对应的关键词直接不搜——搜了也是白搜。
        if avoided & set(need_keys):
            continue
        score = len(needs & set(need_keys)) * 2 + (1 if state.mood_id in moods else 0)
        if score:
            scored.append((score, keyword))
    scored.sort(key=lambda item: -item[0])
    for _score, keyword in scored:
        if keyword not in chosen:
            chosen.append(keyword)
    for keyword in BASELINE_KEYWORDS:
        if keyword not in chosen:
            chosen.append(keyword)
    return chosen[:MAX_KEYWORD_SEARCHES]


KEYWORD_CATEGORY = {keyword: category for keyword, category, _, _ in KEYWORD_PROFILES}
KEYWORD_CATEGORY.update({keyword: category for pairs in PLACE_TYPE_SEARCHES.values() for keyword, category in pairs})


# 缓存下沉到「一个关键词一次搜索」这一层，而不是整次 discover。
# 这样 /interpret 期间预热的「书店/咖啡/公园」，在 /recommendations 里能直接命中，
# 哪怕那时的状态又多点亮了几个别的关键词。
_SEARCH_TTL_SECONDS = 300
_search_cache: dict[tuple[float, float, str], tuple[float, list[dict[str, Any]]]] = {}


async def cached_search(client: AmapClient, location: Location, keyword: str) -> list[dict[str, Any]]:
    # 位置取到小数点后三位（约 100 米）。只在内存里，不写盘、不入库。
    key = (round(location.latitude, 3), round(location.longitude, 3), keyword)
    hit = _search_cache.get(key)
    if hit and (time.monotonic() - hit[0]) < _SEARCH_TTL_SECONDS:
        return hit[1]
    try:
        found = await client.search_around(
            longitude=location.longitude,
            latitude=location.latitude,
            keywords=keyword,
            radius=DISCOVERY_RADIUS_M,
            page_size=DISCOVERY_PAGE_SIZE,
        )
    except MapProviderError:
        # 一个词搜不到不该拖垮其它词——跨境调用本来就会偶发失败。失败不进缓存。
        return []
    _search_cache[key] = (time.monotonic(), found)
    if len(_search_cache) > 256:
        oldest = min(_search_cache, key=lambda k: _search_cache[k][0])
        _search_cache.pop(oldest, None)
    return found


async def warm(client: AmapClient, location: Location) -> None:
    """在别处还在等模型的时候，先把最通用的那几个词搜好。"""
    await asyncio.gather(*(cached_search(client, location, kw) for kw in BASELINE_KEYWORDS))


CATEGORY_PROFILE: dict[str, dict[str, Any]] = {
    "park": {
        "label": "公园 · 户外", "label_en": "park · outdoors",
        "action": "找条长椅坐下，或者随便走走",
        "indoor": False,
        "free": True,
        "crowd": "low",
        "suggested_duration": "30–90 分钟",
        "cost": "不用花钱",
        "see": "开阔的地方，和走不完的路",
        "tags": {"q": 0.7, "g": 0.9, "c": 0.35, "s": 0.85, "co": 0.4, "e": 0.3,
                 "r": 0.85, "cr": 0.2, "l": 0.2, "st": 0.8, "cp": 0.05, "w": 0.9},
    },
    "books": {
        "label": "书店 · 室内", "label_en": "bookshop · indoors",
        "action": "抽一本坐下，不买也行",
        "indoor": True,
        "free": True,
        "crowd": "low",
        "suggested_duration": "30–90 分钟",
        "cost": "可以不消费",
        "see": "一屋子书，和允许你待着的椅子",
        "tags": {"q": 0.85, "g": 0.1, "c": 0.3, "s": 0.9, "co": 0.35, "e": 0.6,
                 "r": 0.75, "cr": 0.7, "l": 0.15, "st": 0.85, "cp": 0.3, "w": 0.1},
    },
    "gallery": {
        "label": "展馆 · 室内", "label_en": "gallery · indoors",
        "action": "慢慢看一圈，不用看完",
        "indoor": True,
        "free": False,
        "crowd": "low",
        "suggested_duration": "40–90 分钟",
        "cost": "可能要买票",
        "see": "别人做的东西，和很高的天花板",
        "tags": {"q": 0.85, "g": 0.15, "c": 0.35, "s": 0.85, "co": 0.3, "e": 0.85,
                 "r": 0.7, "cr": 0.8, "l": 0.15, "st": 0.7, "cp": 0.45, "w": 0.35},
    },
    "cafe": {
        "label": "咖啡 · 室内", "label_en": "coffee · indoors",
        "action": "点一杯，占一张桌子",
        "indoor": True,
        "free": False,
        "crowd": "mid",
        "suggested_duration": "40–90 分钟",
        "cost": "要花点钱",
        "see": "一张属于你的桌子",
        "tags": {"q": 0.6, "g": 0.15, "c": 0.5, "s": 0.8, "co": 0.6, "e": 0.35,
                 "r": 0.7, "cr": 0.5, "l": 0.4, "st": 0.85, "cp": 0.55, "w": 0.1},
    },
    "cinema": {
        "label": "影院 · 室内", "label_en": "cinema · indoors",
        "action": "买一张最近的场次，把手机关掉",
        "indoor": True,
        "free": False,
        "crowd": "mid",
        "suggested_duration": "90–150 分钟",
        "cost": "要买票",
        "see": "两个小时里没人能找到你",
        "tags": {"q": 0.9, "g": 0.05, "c": 0.45, "s": 0.9, "co": 0.25, "e": 0.6,
                 "r": 0.8, "cr": 0.5, "l": 0.1, "st": 0.9, "cp": 0.5, "w": 0.05},
    },
    "temple": {
        "label": "寺庙 · 半户外", "label_en": "temple · part outdoors",
        "action": "进去待一会儿，什么都不用做",
        "indoor": False,
        "free": False,
        "crowd": "low",
        "suggested_duration": "30–60 分钟",
        "cost": "可能要门票",
        "see": "很老的树，和慢下来的人",
        "tags": {"q": 0.9, "g": 0.7, "c": 0.3, "s": 0.85, "co": 0.3, "e": 0.5,
                 "r": 0.9, "cr": 0.25, "l": 0.1, "st": 0.7, "cp": 0.2, "w": 0.6},
    },
}


def _dynamic_profile(
    label: str,
    label_en: str,
    action: str,
    *,
    indoor: bool,
    free: bool,
    crowd: str,
    duration: str,
    cost: str,
    see: str,
    place_types: tuple[str, ...],
    tags: dict[str, float],
) -> dict[str, Any]:
    """让动态类别字段齐全；缺一个字段就会在推荐卡渲染时整条消失。"""
    baseline = {"q": .5, "g": .2, "c": .5, "s": .7, "co": .5, "e": .65,
                "r": .6, "cr": .5, "l": .45, "st": .65, "cp": .55, "w": .2}
    baseline.update(tags)
    return {
        "label": label, "label_en": label_en, "action": action, "indoor": indoor,
        "free": free, "crowd": crowd, "suggested_duration": duration, "cost": cost,
        "see": see, "place_types": list(place_types), "tags": baseline,
    }


# 这些关键词原来能搜到，却因为缺 CATEGORY_PROFILE 被 to_place 静默丢掉。
# 现在每一类都有完整形状，手作、花艺、运动等结果才能真正进入候选集。
CATEGORY_PROFILE.update({
    "tea": _dynamic_profile("茶室 · 室内", "tea house · indoors", "坐下来喝一壶茶",
        indoor=True, free=False, crowd="low", duration="40–90 分钟", cost="需要点茶",
        see="一张能慢慢坐着的茶桌", place_types=("tea",), tags={"q":.85,"r":.8,"l":.15,"st":.85,"c":.25}),
    "records": _dynamic_profile("唱片店 · 室内", "record shop · indoors", "翻一轮唱片，听一张再走",
        indoor=True, free=True, crowd="low", duration="20–60 分钟", cost="可以只听不买",
        see="唱片和可以慢慢翻找的货架", place_types=("records",), tags={"q":.65,"e":.85,"cr":.9,"st":.7,"cp":.25}),
    "vintage": _dynamic_profile("中古店 · 室内", "vintage shop · indoors", "慢慢翻一轮旧物",
        indoor=True, free=True, crowd="low", duration="20–60 分钟", cost="可以只逛不买",
        see="旧衣和旧物，每一件都不太一样", place_types=("vintage",), tags={"e":.95,"cr":.7,"q":.65,"cp":.3}),
    "craft": _dynamic_profile("手作 · 室内", "craft studio · indoors", "选一件手作，把注意力放到手上",
        indoor=True, free=False, crowd="low", duration="60–150 分钟", cost="需要购买体验",
        see="材料、工具和一件能带走的作品", place_types=("craft",), tags={"cr":.95,"r":.75,"q":.7,"st":.9,"cp":.7}),
    "flower": _dynamic_profile("花艺 · 室内", "flower studio · indoors", "挑几枝花，动手做一束",
        indoor=True, free=False, crowd="low", duration="45–120 分钟", cost="需要购买花材或体验",
        see="花材、颜色和能动手完成的东西", place_types=("flower",), tags={"g":.8,"cr":.9,"r":.8,"q":.7,"cp":.7}),
    "music": _dynamic_profile("现场音乐 · 室内", "live music · indoors", "看看最近一场演出",
        indoor=True, free=False, crowd="high", duration="90–180 分钟", cost="通常需要门票",
        see="舞台、音乐和一起听的人", place_types=("music",), tags={"q":.1,"c":.8,"co":.85,"l":.95,"cr":.85,"cp":.65}),
    "river": _dynamic_profile("水边 · 户外", "waterfront · outdoors", "沿着水走一段，随时停下",
        indoor=False, free=True, crowd="low", duration="30–90 分钟", cost="不用花钱",
        see="水面和一条可以继续走的路", place_types=("river",), tags={"g":.65,"q":.75,"r":.9,"w":.95,"cp":.05}),
    "lane": _dynamic_profile("街巷 · 户外", "neighbourhood · outdoors", "沿街慢慢走一圈",
        indoor=False, free=True, crowd="mid", duration="30–90 分钟", cost="走路不用花钱",
        see="街巷、小店和正在发生的生活", place_types=("lane",), tags={"co":.85,"e":.8,"w":.85,"cp":.1}),
    "restaurant": _dynamic_profile("餐厅 · 室内", "restaurant · indoors", "先坐下来吃顿饭",
        indoor=True, free=False, crowd="mid", duration="40–90 分钟", cost="需要用餐",
        see="一顿具体的饭，不用再想下一步", place_types=("restaurant",), tags={"co":.75,"r":.65,"st":.55,"cp":.6}),
    "barbecue": _dynamic_profile("烧烤 · 室内", "barbecue · indoors", "点一份烤串，先把饭吃了",
        indoor=True, free=False, crowd="mid", duration="60–100 分钟", cost="需要用餐",
        see="烤串、热气和一顿具体的饭", place_types=("barbecue","restaurant"), tags={"co":.8,"l":.65,"r":.6,"cp":.65}),
    "hotpot": _dynamic_profile("火锅 · 室内", "hotpot · indoors", "坐下来吃一顿热的",
        indoor=True, free=False, crowd="high", duration="80–150 分钟", cost="需要用餐",
        see="一锅热气和围桌吃饭的人", place_types=("hotpot","restaurant"), tags={"co":.9,"l":.75,"c":.75,"cp":.7}),
    "dessert": _dynamic_profile("甜品 · 室内", "dessert · indoors", "挑一份现在想吃的甜点",
        indoor=True, free=False, crowd="mid", duration="25–70 分钟", cost="需要消费",
        see="一份甜的东西和能坐下的桌子", place_types=("dessert","restaurant"), tags={"r":.7,"st":.65,"cp":.55}),
    "sports": _dynamic_profile("运动场馆 · 室内", "sports venue · indoors", "选一个项目，让身体先动起来",
        indoor=True, free=False, crowd="mid", duration="60–120 分钟", cost="可能需要购票或预约",
        see="可以活动身体的场地", place_types=("sports",), tags={"q":.3,"l":.8,"r":.7,"cr":.4,"st":.75,"cp":.6}),
    "climbing": _dynamic_profile("攀岩馆 · 室内", "climbing gym · indoors", "挑一条简单线路爬一次",
        indoor=True, free=False, crowd="mid", duration="60–120 分钟", cost="需要购票或预约",
        see="岩壁和一条明确的路线", place_types=("climbing","sports"), tags={"q":.45,"l":.65,"r":.75,"cr":.75,"cp":.65}),
    "swimming": _dynamic_profile("游泳馆 · 室内", "swimming pool · indoors", "按自己的速度游几趟",
        indoor=True, free=False, crowd="mid", duration="60–120 分钟", cost="需要购票",
        see="泳池和重复的往返", place_types=("swimming","sports"), tags={"q":.55,"r":.9,"l":.45,"cp":.55}),
    "badminton": _dynamic_profile("羽毛球馆 · 室内", "badminton court · indoors", "约一场球，让身体先接手",
        indoor=True, free=False, crowd="mid", duration="60–120 分钟", cost="需要订场",
        see="球场和能一起打球的人", place_types=("badminton","sports"), tags={"co":.8,"l":.8,"r":.75,"cp":.6}),
    "basketball": _dynamic_profile("篮球馆 · 室内", "basketball court · indoors", "投一会儿篮，让身体先接手",
        indoor=True, free=False, crowd="mid", duration="60–120 分钟", cost="可能需要购票或订场",
        see="球场、篮筐和一起打球的人", place_types=("basketball","sports"), tags={"co":.85,"l":.9,"r":.7,"cp":.55}),
    "tennis": _dynamic_profile("网球场 · 运动", "tennis court", "打一会儿球，把注意力交给身体",
        indoor=False, free=False, crowd="low", duration="60–120 分钟", cost="通常需要订场",
        see="球场和一条清楚的边界线", place_types=("tennis","sports"), tags={"q":.55,"l":.75,"r":.75,"cp":.65,"w":.45}),
    "yoga": _dynamic_profile("瑜伽 · 普拉提 · 室内", "yoga or Pilates · indoors", "跟一节课，把呼吸慢慢放下来",
        indoor=True, free=False, crowd="low", duration="45–90 分钟", cost="通常需要预约课程",
        see="垫子、呼吸和一段不被打断的时间", place_types=("yoga","sports"), tags={"q":.85,"r":.9,"st":.8,"cp":.7}),
    "bar": _dynamic_profile("酒吧 · 室内", "bar · indoors", "找个位子喝一杯",
        indoor=True, free=False, crowd="mid", duration="60–120 分钟", cost="需要点单",
        see="酒、音乐和周围的人", place_types=("bar",), tags={"q":.25,"co":.85,"l":.8,"c":.65,"cp":.75}),
    "club": _dynamic_profile("夜店 · 室内", "club · indoors", "进去跳一会儿，想走就走",
        indoor=True, free=False, crowd="high", duration="90–240 分钟", cost="通常需要门票和饮品",
        see="很响的音乐和一起跳舞的人", place_types=("club",), tags={"q":.05,"co":.9,"l":1.0,"c":.9,"cp":.85}),
    "karaoke": _dynamic_profile("KTV · 室内", "karaoke · indoors", "点一首现在想唱的歌",
        indoor=True, free=False, crowd="mid", duration="90–180 分钟", cost="需要订房",
        see="一个可以大声唱歌的房间", place_types=("karaoke",), tags={"q":.1,"co":.85,"l":.9,"s":.2,"cp":.75}),
})

# Live-search results must still be usable when the copy model is unavailable.
# These are authored fallbacks, not literal translations of the Chinese profile.
DISCOVERY_ACTION_EN: dict[str, str] = {
    "park": "Sit on a bench or take a walk",
    "books": "Pick a book and sit down",
    "gallery": "Walk through one room at your own pace",
    "cafe": "Order one drink and take a table",
    "cinema": "Pick the next screening and put your phone away",
    "temple": "Step inside and stay for a while",
    "tea": "Sit down with a pot of tea",
    "records": "Browse the records and listen before you leave",
    "vintage": "Browse the racks at your own pace",
    "craft": "Pick one small project and use your hands",
    "flower": "Choose a few stems and make a bouquet",
    "music": "See what’s playing next",
    "river": "Walk by the water and stop whenever you like",
    "lane": "Take a slow walk around the neighborhood",
    "restaurant": "Sit down and have a meal",
    "barbecue": "Order some skewers and eat first",
    "hotpot": "Sit down for something hot",
    "dessert": "Choose the dessert you want right now",
    "sports": "Pick one activity and get moving",
    "climbing": "Try one easy route",
    "swimming": "Swim a few laps at your own pace",
    "badminton": "Book a court and play a game",
    "basketball": "Shoot around for a while",
    "tennis": "Play for a while and focus on the ball",
    "yoga": "Take one class and slow your breathing",
    "bar": "Find a seat and have one drink",
    "club": "Dance for a while; leave when you want",
    "karaoke": "Pick one song you want to sing",
}

DISCOVERY_SEE_EN: dict[str, str] = {
    "park": "Open space, paths, and somewhere to sit",
    "books": "Books and somewhere you can pause",
    "gallery": "Exhibitions and room to move slowly",
    "cafe": "A table and a drink",
    "cinema": "A screen and a fixed stretch of time",
    "temple": "Old trees and a slower pace",
    "tea": "A tea table you can stay at",
    "records": "Records and shelves to browse",
    "vintage": "Clothes and objects that are not all the same",
    "craft": "Materials, tools, and one thing to finish",
    "flower": "Flowers, color, and something to make",
    "music": "A stage, music, and other people listening",
    "river": "Moving water and room to keep walking",
    "lane": "Small streets, shops, and everyday life",
    "restaurant": "One concrete meal",
    "barbecue": "Skewers, heat, and a full meal",
    "hotpot": "A hot meal around one table",
    "dessert": "Something sweet and somewhere to sit",
    "sports": "Space to move your body",
    "climbing": "A wall and one clear route",
    "swimming": "A pool and repeatable laps",
    "badminton": "A court and a game to focus on",
    "basketball": "A court, a hoop, and room to move",
    "tennis": "A court and clear boundary lines",
    "yoga": "A mat, your breathing, and an uninterrupted class",
    "bar": "A drink, music, and people nearby",
    "club": "Loud music and room to dance",
    "karaoke": "A room where you can sing out loud",
}


def _discovery_cost_en(category: str, profile: dict[str, Any]) -> str:
    if profile["free"]:
        return "Free"
    if category in {"cafe", "tea", "restaurant", "barbecue", "hotpot", "dessert", "bar"}:
        return "You’ll need to order."
    if category in {"records", "vintage"}:
        return "Browsing is free; buying is optional."
    if category in {"craft", "flower", "sports", "climbing", "swimming", "badminton", "basketball", "tennis", "yoga", "karaoke"}:
        return "Booking or admission may be required."
    return "Admission may be required."

# 高德会把「打卡点」「出入口」「停车场」这类东西也当 POI 返回。
# 它们不是能待的地方，推给一个正难受的人是冒犯。
# 连锁店没有叙事。一个正难受的人不需要被推荐去楼下那家瑞幸——
# 那是大众点评在做的事，不是我们。
CHAIN_BRANDS: tuple[str, ...] = (
    "星巴克", "Starbucks", "瑞幸", "luckin", "Manner", "喜茶", "奈雪", "蜜雪",
    "COSTA", "Costa", "太平洋咖啡", "Tims", "库迪", "麦当劳", "肯德基", "必胜客",
    "沪上阿姨", "古茗", "茶百道", "书亦", "CoCo", "一点点", "霸王茶姬", "大益茶",
    "全家", "7-ELEVEN", "罗森", "便利蜂", "万达", "横店电影城", "CGV", "金逸",
    "大地影院", "博纳影城", "百丽宫", "耀莱", "新华书店", "西西弗",
)

NOISE_PATTERNS: tuple[str, ...] = (
    "打卡点", "出入口", "入口", "出口", "停车场", "停车楼", "收费站", "厕所", "洗手间",
    "售票", "服务中心", "办公室", "管理处", "施工", "暂停营业", "已关闭", "内部",
    "候车", "公交站", "地铁站", "充电站", "报刊亭", "自动售", "取款机", "门诊", "医院",
    # 进不去的地方比推荐得不准更糟——人真的会走过去。
    "不对外开放", "不开放", "谢绝参观", "暂不开放", "预约制", "闭馆",
    # 公司、网站、机构被当成 POI 返回，它们不是能待的地方。
    "有限公司", "收藏网", "鉴定", "商会", "事务所", "工作室招聘", "研究所", "协会",
)

# 太短或者全是符号的名字多半是数据噪声。
_NAME_OK = re.compile(r"[一-鿿A-Za-z]{2,}")

# 「星巴克(国贸四店)」和「星巴克(世界财富大厦WWT店)」是同一件事。
# 括号里的分店名去掉之后就能看出是不是同一个品牌。
_BRANCH_SUFFIX = re.compile(r"[(（\[].*?[)）\]]|\s*[·\-—]\s*\S*店$")

# 一次最多给几个同类。六家咖啡馆并排列出来，等于没有选择。
PER_CATEGORY_CAP = 2


def _brand_of(name: str) -> str:
    return _BRANCH_SUFFIX.sub("", name).strip() or name


# 「故宫博物院-神武门广场」「上海大剧院-中剧场」这种是大景点的子设施，
# 不是一个能带着情绪去待着的地方。
_SUB_POI_TAIL = ("门", "殿", "广场", "馆", "厅", "处", "楼", "区", "口", "点", "部")


def _is_sub_poi(name: str) -> bool:
    if "-" not in name:
        return False
    tail = name.rsplit("-", 1)[-1].strip()
    return bool(tail) and tail.endswith(_SUB_POI_TAIL)


def _looks_like_noise(name: str) -> bool:
    if not name or not _NAME_OK.search(name):
        return True
    if _is_sub_poi(name):
        return True
    if any(brand in name for brand in CHAIN_BRANDS):
        return True
    return any(pattern in name for pattern in NOISE_PATTERNS)


def _photo_urls(poi: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for photo in poi.get("photos") or []:
        url = str((photo or {}).get("url") or "").strip()
        # 高德返回的是 http，页面是 https，混合内容会被浏览器拦掉。
        if url.startswith("http://"):
            url = "https://" + url[len("http://"):]
        if url.startswith("https://"):
            urls.append(url)
    return urls[:3]


def to_place(poi: dict[str, Any], category: str) -> dict[str, Any] | None:
    """把一个高德 POI 变成和人工地点同一个形状。类别由搜它的那个关键词决定。"""
    name = str(poi.get("name") or "").strip()
    if _looks_like_noise(name):
        return None
    profile = CATEGORY_PROFILE.get(category)
    if not profile:
        return None
    photos = _photo_urls(poi)
    if not photos:
        # 没有照片的现场结果不要。#2 的整个意义就是让人看见真实的地方，
        # 一张没有的话，它在卡片上还是一个抽象符号。
        return None

    provider_id = str(poi.get("id") or "")
    distance_m = float(poi.get("distance") or 0)
    english_category = profile.get("label_en") or profile["label"]
    english_kind = str(english_category).split(" · ")[0]
    return {
        "placeId": f"amap:{provider_id}",
        "placeName": name,
        "action": profile["action"],
        "action_en": DISCOVERY_ACTION_EN.get(category, f"Spend a little time at this {english_kind}"),
        "area": str(poi.get("adname") or poi.get("cityname") or ""),
        "category": profile["label"],
        "category_en": english_category,
        "city": str(poi.get("cityname") or ""),
        # 公交路线要城市编码。周边搜索本来就返回它，捡起来用，
        # 免得为了一条公交路线再去做一次逆地理编码。
        "citycode": str(poi.get("citycode") or ""),
        "coverImage": f"photo:{photos[0]}",
        "photos": photos,
        "ratio": "4/5",
        "distanceKm": round(distance_m / 1000, 2) if distance_m else None,
        "transport": str(poi.get("address") or ""),
        "suggestedDuration": profile["suggested_duration"],
        "suggestedDuration_en": str(profile["suggested_duration"]).replace(" 分钟", " min"),
        "indoor": profile["indoor"],
        "free": profile["free"],
        "crowd": profile["crowd"],
        "see": profile["see"],
        "cost": profile["cost"],
        "see_en": DISCOVERY_SEE_EN.get(category, f"A nearby {english_kind}"),
        "cost_en": _discovery_cost_en(category, profile),
        "placeTypes": list(profile.get("place_types") or [category]),
        "environmentTags": [],
        "tags": dict(profile["tags"]),
        # 这一类的常识，不是对这一家的判断——所以只有一条 "_"，而且措辞留余地。
        "matchReason": {"_": f"{profile['label'].split(' · ')[0]}这一类，通常能接住你现在说的这种状态。"},
        "matchReason_en": {"_": f"A nearby {english_kind} is one concrete match for what you asked for."},
        "placeInsights": [],
        "factors": [],
        "averageChange": None,
        "feedbackCount": 0,
        "source": "discovered",
        "amap": {
            "provider_place_id": provider_id,
            "longitude": float(poi["longitude"]),
            "latitude": float(poi["latitude"]),
            "verified_name": name,
            # 坐标就是这个 POI 自己的记录，不是我们把一个名字硬套到某个 POI 上——
            # 所以可以导航。但它拿不到围栏在场证明（见模块开头那张表）。
            "verification_status": "provider_exact",
        },
        "hours": {"open_time_today": str(((poi.get("business") or {}) if isinstance(poi.get("business"), dict) else {}).get("opentime_today") or "")},
    }


async def discover(
    client: AmapClient,
    location: Location,
    state: NeedState,
    *,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """按用户此刻的位置和状态搜一圈，返回能用的候选。搜不到就返回空——绝不编。"""
    if not client.configured:
        return []

    chosen = keywords_for(state)

    async def search(keyword: str) -> tuple[str, list[dict[str, Any]]]:
        return keyword, await cached_search(client, location, keyword)

    groups = await asyncio.gather(*(search(keyword) for keyword in chosen))

    places: list[dict[str, Any]] = []
    seen_brands: set[str] = set()
    seen_ids: set[str] = set()
    per_category: dict[str, int] = {}

    # 交替取，让各类别机会均等，而不是排第一的关键词把名额占完。
    rows = zip_longest(*[[(keyword, poi) for poi in found] for keyword, found in groups])
    flat = [item for row in rows for item in row if item]
    for keyword, poi in flat:
        place = to_place(poi, KEYWORD_CATEGORY.get(keyword, ""))
        if not place:
            continue
        if place["placeId"] in seen_ids:
            continue
        # 用户说了「想待在室内 / 想在户外」，现场结果也得听。
        if state.environment == "indoor" and not place["indoor"]:
            continue
        if state.environment == "outdoor" and place["indoor"]:
            continue
        brand = _brand_of(place["placeName"])
        if brand in seen_brands:
            continue
        category = place["category"]
        if per_category.get(category, 0) >= PER_CATEGORY_CAP:
            continue
        seen_ids.add(place["placeId"])
        seen_brands.add(brand)
        per_category[category] = per_category.get(category, 0) + 1
        place["found_by"] = keyword
        places.append(place)
        if len(places) >= limit:
            break
    return places
