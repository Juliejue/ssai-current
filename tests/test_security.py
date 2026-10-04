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


def test_current_model_studio_workspace_is_allowed_without_wildcards(monkeypatch):
    monkeypatch.delenv("LLM_ALLOWED_HOSTS", raising=False)
    host = "ws-6hporszsrl78pmws.ap-southeast-1.maas.aliyuncs.com"
    base = "https://" + host + "/compatible-mode/v1"
    assert checked_model_base_url(base) == base
    assert checked_model_base_url("https://another-workspace.ap-southeast-1.maas.aliyuncs.com/v1") is None
    assert checked_model_base_url("https://" + host + ".evil.example/v1") is None
    assert checked_model_base_url("http://" + host + "/v1") is None
    assert checked_model_base_url("https://user:password@" + host + "/v1") is None
