# 本地代理客户端配置 & 使用经验

本目录沉淀如何在本地 **Clash Verge**（mihomo 内核）使用本项目部署在 Oracle VM 上的
**orc-holo** 节点（3x-ui / VLESS + Reality，端口 8443），以及从机场客户端 **Crown**
迁移过程中总结的经验，供日后参考。

## 文件

| 文件 | 说明 | Git |
|---|---|---|
| `orc-holo.clash.yaml` | 真实可用配置（含节点凭据） | **gitignored** |
| `orc-holo.clash.example.yaml` | 脱敏模板 | 入库 |
| `README.md` | 本文档 | 入库 |

## 节点信息（orc-holo）

- 协议：VLESS + Reality / TCP，`flow: xtls-rprx-vision`
- 服务器：VM 公网 IP（`uv run oci-vm cloud ip`），端口 `8443`
- SNI 伪装：`www.microsoft.com`，`client-fingerprint: chrome`
- 凭据（UUID / public-key / short-id）：存于 VM 的 3x-ui，**不入库**，见下方「重新生成配置」

> ⚠️ VM 默认是**临时公网 IP（ephemeral）**：`cloud stop/start` 重启实例后 IP 可能变，
> 届时要更新配置里的 `server`（或在 OCI 把公网 IP 转成 Reserved 固定下来）。

## 在 Clash Verge 集成

1. 用现成的 `orc-holo.clash.yaml`，或复制 `*.example.yaml` 填入真实值。
2. Clash Verge → 订阅/Profiles → 新建 → **Local** → 选该 yaml → 保存并**生效**。
3. 「代理」页：`NORMAL` 和 `AI` 两组都选 `orc-holo`。
4. 打开「**系统代理**」开关。⚠️ 系统代理同一时刻只能归一个客户端——若还开着 Crown，先关掉它的系统代理。

## 配置结构

- **两个代理组**（语义对称、各管一类流量）：
  - `NORMAL` — 普通墙外流量（`orc-holo` / `DIRECT` 可选）
  - `AI` — AI 服务专用（`orc-holo`，回退 `NORMAL`）。单节点下与 NORMAL 等价，
    保留它是为**可扩展**：以后加别的地区节点，可专门给 AI 挑最干净的出口。
- **规则顺序**：AI 域名显式优先 → `GEOIP,CN,DIRECT`（国内直连）→ `MATCH,NORMAL`（其余走代理）。
- **DNS**：`fake-ip` 模式，走代理的域名由节点远程解析（天然抗 DNS 污染），DoH 兜底。

## 参考 Crown（机场客户端）的经验

迁移自商业机场客户端 Crown（BlackSSL/DarkSSL，Flutter + 内置 mihomo，端口 1234/1235）：

### 1. AI 工具：自建独享 IP 优于机场共享 IP
机场是**大量用户共享同一批出口 IP**，最容易被 OpenAI/Claude 风控（验证码、限速、封锁）；
orc-holo 是**独享固定美国 IP**，行为干净，对 AI 更稳。代价是单节点（无备份出口）。

### 2. orc-holo 出口 IP 对 AI 的实测（2026-06-18）
从 VM 出口实测（即 orc-holo 的真实出口）：

| 服务 | 结果 | 解读 |
|---|---|---|
| IP / 地区 | Oracle · 美国凤凰城 · `loc=US` | 三家 AI 的支持区 |
| OpenAI API | `401` | IP 可达、未被封 |
| Anthropic API | `405` | IP 可达、未被封 |
| Gemini / AI Studio | `200` / `302` | 完全正常 |
| ChatGPT / Claude 网页 | `403`（curl） | Cloudflare 拦命令行，真浏览器可过 |

> 结论：IP 在地区/封禁层面是干净的；不做人机验证的 **API 端点全部可达**是最强信号。
> ChatGPT/Claude 用浏览器访问应正常，切换后建议用浏览器实测确认一次。

### 3. AI 分流规则借鉴
Crown 把 Gemini / ChatGPT / Claude 的域名单独导到一个 AI 组——这个思路被搬进了本配置的 AI 规则段。

### 4. 组命名
`AI` / `NORMAL` 比 `AI` / `PROXY` 更好：两者都是「流量类别」、语义对称；且该组也能选 `DIRECT`，
叫 `NORMAL`（普通流量）比 `PROXY`（暗示必走代理）更准确。

## 运维 / 排查经验

### 代理类「断网」三步排查
关闭 Clash Verge 后，Windows 系统代理可能被置成 `ProxyEnable=0`，浏览器变裸连 →
**国内站正常、墙外站打不开**，看着像断网，其实是没代理了。排查：
1. 注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings` 的 `ProxyEnable` / `ProxyServer`
2. 哪个代理端口在监听：`Get-NetTCPConnection -State Listen -LocalPort 7890,7897,1234,1235`
3. 有无残留 TUN 虚拟网卡
对比「国内站能开 + 墙外站错误页」即可锁定“无代理→被墙”，而非网络故障。

### 端口对照
| 客户端 | mixed/HTTP | SOCKS | 控制器 |
|---|---|---|---|
| Clash Verge | 7897 | 7891 | 9090 |
| Crown | 1235 | 1234 | 9090 |

> 两者端口不冲突，可并存安装；但**系统代理同一时刻只能归一个**。

## 重新生成配置（IP 变了 / 凭据轮换后）

节点参数存在 VM 的 3x-ui SQLite 数据库（`/home/ubuntu/docker/3x-ui/db/x-ui.db`）。
最省事是登录 3x-ui 面板复制 VLESS 分享链接；或用脚本只读提取（不输出私钥）：

```bash
uv run oci-vm cloud ip                       # 1) 拿公网 IP → 填 server
uv run oci-vm run "python3 - <<'PY'
import sqlite3, json
con = sqlite3.connect('file:/home/ubuntu/docker/3x-ui/db/x-ui.db?mode=ro', uri=True)
con.row_factory = sqlite3.Row
for r in con.execute('select * from inbounds'):
    d = dict(r)
    if d['protocol'] != 'vless':
        continue
    s = json.loads(d['settings']); st = json.loads(d['stream_settings'])
    rs = st.get('realitySettings', {}); sub = rs.get('settings', {})
    print('uuid      :', s['clients'][0]['id'])
    print('flow      :', s['clients'][0].get('flow'))
    print('serverName:', rs.get('serverNames'))
    print('publicKey :', sub.get('publicKey'))
    print('shortIds  :', rs.get('shortIds'))
PY"
```

### 复测节点对 AI 的可达性
```bash
uv run oci-vm run "curl -s https://www.cloudflare.com/cdn-cgi/trace | grep -E '^ip=|^loc='; \
  for u in https://api.openai.com/v1/models https://api.anthropic.com/v1/messages https://gemini.google.com/; do \
    curl -s -o /dev/null -w \"\$u -> %{http_code}\n\" -A Mozilla/5.0 \$u; done"
```

---
最后更新：2026-06-18
