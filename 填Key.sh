#!/usr/bin/env bash
# 把 Key 填进本地 .env，不经过终端历史、不进 Git。
# 用法：bash 填Key.sh
# 每一项都可以直接回车跳过，之后再跑一次补上。
set -u
cd "$(dirname "$0")"
[ -f .env ] || cp .env.example .env

set_key () {  # set_key 变量名 提示语
  local name="$1" prompt="$2" value=""
  printf '\n%s\n' "$prompt"
  read -r -s -p "  $name = " value; echo
  [ -z "$value" ] && { echo "  （跳过）"; return; }
  # 用 python 改写，避免 sed 在含 / & 的连接串上出问题
  python3 - "$name" "$value" <<'PY'
import pathlib, sys
name, value = sys.argv[1], sys.argv[2]
p = pathlib.Path(".env")
lines = p.read_text(encoding="utf-8").splitlines()
done = False
for i, line in enumerate(lines):
    if line.startswith(name + "="):
        lines[i] = f'{name}="{value}"'
        done = True
        break
if not done:
    lines.append(f'{name}="{value}"')
p.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
  echo "  ✓ 已写入 .env"
}

echo "输入时不会显示，直接粘贴然后回车就行。不想填的直接回车跳过。"
set_key DATABASE_URL          "① Neon：Connect 弹窗里那条（主机名必须带 -pooler）"
set_key LLM_API_KEY           "② 智谱：open.bigmodel.cn → API Keys"
set_key TENCENT_SECRET_ID     "③ 腾讯云：访问管理 → API 密钥管理 → SecretId"
set_key TENCENT_SECRET_KEY    "④ 腾讯云：同上 → SecretKey"
set_key ASR_APP_ID            "⑤ 腾讯云：语音识别 → 应用管理 → AppID"
set_key AMAP_WEB_SERVICE_KEY  "⑥ 高德：应用管理 → Key（服务平台必须是「Web服务」）"

echo
echo "填好了。现在的状态："
python3 - <<'PY'
import pathlib
for line in pathlib.Path(".env").read_text(encoding="utf-8").splitlines():
    if "=" not in line or line.startswith("#"):
        continue
    k, _, v = line.partition("=")
    if k in ("ALLOWED_ORIGINS", "LLM_BASE_URL", "LLM_MODEL", "ASR_ENGINE_MODEL"):
        continue
    print(f"  {k:22} {'已填 ' + str(len(v)) + ' 位' if v.strip() else '还空着'}")
PY
echo
echo "回去告诉 Claude「填好了」，剩下的交给它。"
