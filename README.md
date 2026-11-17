# rules —— 自用分流规则（单一源 + 多客户端产物）

一份规则源（`sources/`），由脚本生成 Surge / Loon / Quantumult X / Clash / Egern 各端产物（`dist/`）。
GitHub Action 每天 07:30（北京时间）拉取上游规则、合并去重、重建产物并提交。

## 设计

```
sources/*.txt        手写规则（Surge 语法，单一源）  ← 只改这里
sources/auto/*.txt   Action 从上游采集合并的规则     ← 只改 upstreams.yml
scripts/collect.py   多元采集：拉上游 → 归一化 → 去重
scripts/build.py     单一源 → 各客户端产物（dist/）
dist/{surge,quantumultx,clash,egern}/*.list|.yaml
```

- **策略不写进规则文件**：统一在客户端引用处指定。这样同一份文件可以被任意策略组复用。
- 去重按 `类型,值` 做，输出排序固定 → git diff 可读。
- 单个上游超时/失败只跳过它，不影响其他源；全部失败则保留上次产物。

## 订阅地址

把 `<名字>` 换成下表，`<分支>` 为 `main`：

| 客户端 | 地址 |
|---|---|
| Surge / **Loon** / Shadowrocket | `https://raw.githubusercontent.com/<你>/rules/main/dist/surge/<名字>.list` |
| Quantumult X | `https://raw.githubusercontent.com/<你>/rules/main/dist/quantumultx/<名字>.list` |
| Clash / Mihomo / Stash | `https://raw.githubusercontent.com/<你>/rules/main/dist/clash/<名字>.yaml` |
| **Egern** | `https://raw.githubusercontent.com/<你>/rules/main/dist/egern/<名字>.yaml`，或直接用上面 Surge 的 `.list`（Egern 支持 Surge 规则集） |

国内 raw 不稳时把 `https://raw.githubusercontent.com/<你>/rules/main/` 换成
`https://cdn.jsdelivr.net/gh/<你>/rules@main/`（有 12–24h 缓存延迟）。

## 规则集

| 名字 | 内容 | 建议策略 |
|---|---|---|
| `us-finance` | 美国银行 / 发卡行 / 券商 / 支付 / 风控指纹 / 征信（73 域） | 固定美国住宅 IP |
| `us-finance-idv` | Plaid / Yodlee / Finicity / id.me / Jumio 等（8 域） | 同 `us-finance` |
| `ai` | AI 服务，多源合并去重（420+ 域） | AI 策略组 |
| `tu-proxy` | 需要走代理的个人站点 | 起飞出国 |
| `tu-direct` | 国内直连 | 国内直连 |
| `tu-adblock` | 广告拦截补充 | 广告拦截 |

## 加一条规则

1. 改 `sources/<名字>.txt`，加一行 `DOMAIN-SUFFIX,example.com`
2. 本地 `python3 scripts/build.py`（只改上游才需要跑 `collect.py`）
3. 提交；Action 也会在下次运行时重建

## Egern 引用示例

```yaml
rules:
  - rule_set:
      name: 美国金融
      match: https://raw.githubusercontent.com/<你>/rules/main/dist/egern/us-finance.yaml
      policy: 美国金融
      disabled: false
```

同一个文件还能给 DNS 段复用（让解析走同一出口）：

```yaml
dns:
  forward:
    - proxy_rule_set:
        match: https://raw.githubusercontent.com/<你>/rules/main/dist/egern/us-finance.yaml
        value: 国外DNS
```

## 已知限制

- 生成器只处理域名/IP 类规则；`PROCESS-NAME`、`AND/OR/NOT` 等特性各端不通用，遇到会跳过并告警。
- sing-box 产物尚未生成（需要 `.srs` 二进制或 JSON 规则集），需要时再加一个 writer。
- 上游采集依赖公网可达；若某个上游长期超时，把它从 `upstreams.yml` 删掉即可。
