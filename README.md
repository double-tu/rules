# rules —— 自用分流规则（单一源 + 多客户端产物）

一份规则源（`sources/`），由脚本生成 Surge / Loon / Quantumult X / Clash / Egern 各端产物（`dist/`）。
GitHub Action 每天 07:30（北京时间）拉取上游规则、合并去重、重建产物并提交。

## 设计

```
sources/<名字>.txt        手写白名单（长期有效，上游挂了也不丢）
sources/auto/<名字>.txt   每天从上游聚合（改 upstreams.yml）
scripts/collect.py        并发拉取 → 格式识别 → 归一化 → 去重 → 缓存/镜像回退
scripts/build.py          手写 + 采集 合并去重 → 4 种客户端产物 + data/counts.json
scripts/guard.py          和上一个提交比，单类目掉 >30% 直接失败
scripts/status.py         生成 STATUS.md（每类目条目数 + 每上游拉取状态）
scripts/check.py          产物校验（非空/无重复/分组有序/三端一致）
dist/{surge,quantumultx,clash,egern}/*.list|.yaml
```

### 四道保险（参考 VPSDance/ai-proxy-rules）

| 机制 | 解决的问题 |
|---|---|
| **缓存 + 镜像** | 上游超时/404 时自动改用 jsdelivr 重试；仍失败则回退 `data/cache/` 上次内容（CI 里用 `actions/cache` 持久化，不污染仓库） |
| **Guard** | 某个类目规则数比上次提交掉超过 30% 就判失败 —— 对应「Repcz 删文件导致 Gemini 静默失效」这类事故 |
| **状态表** | `STATUS.md` 自动列出每个类目条目数与每个上游的成功/缓存/失败状态 |
| **产物校验** | 四种格式条目数必须一致、无重复、分组内有序、非空 |

### 数据质量

上游常混入单标签条目（`DOMAIN-SUFFIX,hsbc`、`DOMAIN-SUFFIX,youtube` 这种）。
它们不会劫持大流量（`*.<label>` 才匹配），但属于噪音：`build.py` 会统计并写入
`data/warnings.json`，`STATUS.md` 可见。只有 `DOMAIN-SUFFIX,com/net/org` 这种顶级域会直接判失败。

### 重类目与更新节奏

| 类目 | 条目 | 说明 |
|---|---:|---|
| `cn-direct` | 110,243 | 只保留 **Loyalsoldier direct 单一权威源**。ChinaMax 与它重合 **97.6%**（110,478 vs 110,195，并集只多 2,317 条），两份一起合并等于用两倍体积换 2% 覆盖 |
| `proxy-global` | 32,470 | Loyalsoldier proxy + Repcz Proxy 合并（单份最大 27,358，合并 +5,112 条，+19%） |

这两个类目标了 `heavy: true`：**日更 workflow 跳过它们，由 `build-heavy.yml` 每周日 08:00 单独重建**。
理由：它们占全部产物体积的 80%+，每天提交会让仓库以 MB 级速度膨胀，而域名清单周更完全够用。

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
| **Loon** | `https://raw.githubusercontent.com/<你>/rules/main/dist/loon/<名字>.list`（与 surge 语法相同，单独目录便于区分） |
| **sing-box** | `https://raw.githubusercontent.com/<你>/rules/main/dist/sing-box/<名字>.json`（rule-set source 格式，`{"version":1,"rules":[...]}`；`type: remote, format: source`） |
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
