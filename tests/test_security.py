from backend_app.security import checked_model_base_url


def test_model_egress_allows_only_configured_https_hosts(monkeypatch):
    monkeypatch.delenv("LLM_ALLOWED_HOSTS", raising=False)
    assert checked_model_base_url("https://open.bigmodel.cn/api/paas/v4/") == "https://open.bigmodel.cn/api/paas/v4"
    for url in (
        "http://open.bigmodel.cn/api/paas/v4",
        "https://127.0.0.1/v1",
        "https://169.254.169.254/latest/meta-data",
        "https://open.bigmodel.cn.evil.example/v1",
        "https://user:password@open.bigmodel.cn/v1",
        "https://localhost/v1",
        "https://api.openai.com:8443/v1",
    ):
        assert checked_model_base_url(url) is None

    monkeypatch.setenv("LLM_ALLOWED_HOSTS", "model.example.com")
    assert checked_model_base_url("https://model.example.com/v1") == "https://model.example.com/v1"
