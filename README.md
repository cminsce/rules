# 个人分流规则：Surge / Loon / Quantumult X / Stash

维护一份个人规则源，生成四款 App 的原生规则集和接入片段。沿用现有节点、订阅、DNS 和兜底规则，仅增加个人分流。

**本次重整不保留根目录旧 `Custom*.list` 地址。** 请将旧引用切换到对应客户端的 `rules/` 路径。7 份名单统一在 `source/` 中维护；`CustomReject.list` 已改名为 `RednoteReject.list`。

## 选择对应 App

| App | 规则目录 | 接入片段 | 合并位置 |
| --- | --- | --- | --- |
| Surge | [rules/surge](rules/surge) | [surge.conf](config/surge.conf) | `[Rule]` |
| Loon | [rules/loon](rules/loon) | [loon.conf](config/loon.conf) | `[Remote Rule]` |
| 圈 X / Quantumult X | [rules/quantumult-x](rules/quantumult-x) | [quantumult-x.conf](config/quantumult-x.conf) | `[filter_remote]` |
| Stash | [rules/stash](rules/stash) | [stash.yaml](config/stash.yaml) | `rule-providers` 和 `rules` |

这些文件是**接入片段，不是完整主配置**，不能直接替换 App 当前配置。

1. 确认对应规则文件已发布到 GitHub 的 `main` 分支；本地生成不会上传文件。
2. 根据下表，将接入片段中的策略名称改为该 App **已经存在**的策略组或节点名称。
3. 将片段合并到表中对应位置；已有同名区块时仅合并内容，不再添加重复区块。
4. 在 App 中更新远程规则，通过请求记录检查命中规则和最终节点。

接入片段默认引用本仓库，例如 [Surge 的 CustomProxy 原始文件](https://raw.githubusercontent.com/cminsce/surge-rules/main/rules/surge/CustomProxy.list)。订阅要使用 `raw.githubusercontent.com` 地址，不能使用 GitHub 的文件展示页面。

## 分类与策略

以下名称来自原规则注释，是接入示例的默认映射。策略组名称相同不代表其成员相同；请确认各 App 的组内选择符合预期。

| 规则集 | 用途 | 源规则数 | 默认策略 | 需要对应的现有节点/策略 |
| --- | --- | ---: | --- | --- |
| `RednoteReject` | 小红书拦截 | 10 | `REJECT` | 内置拒绝策略；Loon 输出 9 条，见下文 |
| `CustomDirect` | 强制直连 | 9 | `DIRECT` | 内置直连策略 |
| `CustomAd` | 个人广告/统计拦截 | 246 | `REJECT` | 内置拒绝策略 |
| `CustomDownload` | 下载分流 | 18 | `Ⓜ️ 微软云盘` | 原费利蒙下载节点，或你的下载策略组 |
| `CustomJapan` | 日本分流 | 19 | `📲 电报消息` | 日本节点/策略组 |
| `CustomUS3` | 美国分流 | 71 | `📢 谷歌FCM` | 原美国节点 3，或你的美国策略组 |
| `CustomProxy` | 通用代理 | 30 | `🚀 节点选择` | 通用代理策略组 |

源名单共 403 条。`otheve.beacon.qq.com` 已从原 `CustomReject.list` 移入 `CustomAd.list`，其余域名及所属分类保持不变。

接入片段顺序为：小红书拦截 → 强制直连 → 广告拦截 → 下载 → 日本 → 美国 → 通用代理。将这些个人规则置于现有通用订阅规则之前；客户端本身的匹配优先级仍然适用。

## 各 App 接入要点

### Surge

复制 [surge.conf](config/surge.conf) 中的 `RULE-SET` 行到现有 `[Rule]` 前部。保持现有 `FINAL` 在最后；不要同时引用已迁移的旧根目录文件。

规则文件采用 `类型,匹配值` 两列格式，策略在 `RULE-SET,URL,策略` 中绑定，按 [Surge 官方规则集文档](https://manual.nssurge.com/rules/ruleset.html)组织。

### Loon

复制 [loon.conf](config/loon.conf) 的订阅行到现有 `[Remote Rule]` 前部，通过 `policy=` 选择对应策略；语法见 [Loon 官方示例](https://github.com/Loon0x00/LoonExampleConfig/blob/master/example.conf)。保留现有 `[Rule]` 和 `FINAL`。按照 [Loon 匹配优先级](https://nsloon.app/docs/Rule/)，本地和插件规则优先于订阅；有冲突时，需要调整优先命中的那条规则。

**Loon 的通配符覆盖不完整：** [官方域名规则文档](https://nsloon.app/docs/Rule/domain_rule/)只列出 `DOMAIN`、`DOMAIN-SUFFIX`、`DOMAIN-KEYWORD`，没有与 `DOMAIN-WILDCARD` 等价的规则。本仓库因此不向 Loon 输出 `ads-*.xhscdn.com` 通配符，仅保留源文件中已有的 5 个精确域名：

```text
ads-img-al.xhscdn.com
ads-img-qc.xhscdn.com
ads-video-al.xhscdn.com
ads-video-qc.xhscdn.com
ads-vp5.xhscdn.com
```

未知的 `ads-*` 域名不会被这 5 条规则拦截。Loon 产物和生成日志也标注此差异，未用整个 `xhscdn.com` 的后缀拦截替代。新增通配符会令生成失败，需要先明确其 Loon 适配方式。

### Quantumult X（圈 X）

复制 [quantumult-x.conf](config/quantumult-x.conf) 的订阅行到现有 `[filter_remote]`，将每行 `force-policy=` 改为实际策略名。内置直连和拒绝使用小写 `direct`、`reject`。

规则已转换为 `host`、`host-suffix`、`host-keyword`、`host-wildcard`，每行自带默认策略。`force-policy` 可以覆盖文件内策略；这是原生圈 X 格式，接入片段设置 `opt-parser=false`，无需资源解析器。语法和覆盖方式见 [官方 sample.conf](https://github.com/crossutility/Quantumult-X/blob/master/sample.conf)。保留现有 `[filter_local]` 与 `final`，并检查原有本地规则是否影响命中。

### Stash

将 [stash.yaml](config/stash.yaml) 中的 7 个 provider 合并进现有 `rule-providers`，再将 7 条 `RULE-SET` 插到现有 `rules` 前部。每条 `RULE-SET` 最后的字段是策略名。保持原有 `MATCH` 兜底规则在最后。

规则文件使用 `payload` YAML，provider 指定 `behavior: classical` 和 `format: yaml`，以同时支持精确域名、后缀、关键词和通配符。格式见 [Stash 规则集文档](https://stash.wiki/en/rules/rule-set)。

`RednoteReject` 保留 `DOMAIN-WILDCARD`，需使用支持该规则的 Stash 版本；iOS 版在 [3.0.1 更新](https://stash.wiki/release-notes/ios)中加入了该类型。不要将这些规则文件声明为 `behavior: domain`。

## 维护

```text
source/                 # 唯一需要维护的域名名单
rules/surge/            # 自动生成的 Surge 规则
rules/loon/             # 自动生成的 Loon 规则
rules/quantumult-x/      # 自动生成的圈 X 规则
rules/stash/            # 自动生成的 Stash YAML
config/                 # 自动生成的四端接入片段
scripts/build_rules.py  # 转换与校验，仅使用 Python 标准库
tests/                  # 转换、引用和失败场景测试
```

维护环境为 Python 3.10+，无需安装第三方依赖。修改 `source/` 后运行：

```sh
python3 scripts/build_rules.py
python3 -m unittest discover -s tests -v
python3 scripts/build_rules.py --check
```

将源文件与生成产物一起提交。GitHub Actions 会检查转换测试和产物同步状态，不会自动提交或推送。

源文件当前支持无策略的 `DOMAIN`、`DOMAIN-SUFFIX`、`DOMAIN-KEYWORD`、`DOMAIN-WILDCARD`。不支持的类型、额外参数、重复项、空规则集、未登记的源文件都会报错，不会静默丢弃。新增类别时，在 `scripts/build_rules.py` 的 `RULESETS` 中登记名称、默认策略和接入顺序；四端接入片段会一并更新。

策略名称通常在 App 内按需调整。若要统一更改仓库产物的默认策略，修改 `RULESETS` 后重新生成；直接编辑 `rules/` 或 `config/` 会在下次生成时被覆盖。

Fork 或更换分支时，修改脚本中的 `BASE_URL` 并重新生成，使 CI 使用同一地址。临时预览也可使用：

```sh
python3 scripts/build_rules.py --base-url https://raw.githubusercontent.com/你的用户名/你的仓库/main
python3 scripts/build_rules.py --check --base-url https://raw.githubusercontent.com/你的用户名/你的仓库/main
```

本地检查验证转换结果、引用和产物一致性，不等同于四款 App 的真实加载或联网测试。接入后可检查 `ci.xiaohongshu.com` 是否直连、`ads-img-al.xhscdn.com` 是否拒绝，以及各地区规则是否命中所选节点。
