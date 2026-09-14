from backend_app.schemas import ProductEvent
from backend_app.storage import safe_event_properties


def test_event_properties_are_allowlisted():
    payload = ProductEvent(
        name="natural_language_interpreted",
        session_id="ses_12345678",
        properties={
            "source": "rules",
            "mood_id": "low",
            "raw_text": "这是不应进入分析的数据",
            "latitude": 39.9,
            "name": "某个人",
        },
    )
    assert safe_event_properties(payload) == {"source": "rules", "mood_id": "low"}
