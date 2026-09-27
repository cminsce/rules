#!/usr/bin/env python3
"""Generate client rule sets and configuration fragments using only the stdlib."""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://raw.githubusercontent.com/cminsce/surge-rules/main"
CLIENTS = ("surge", "loon", "quantumult-x", "stash")
# Order is shared by all configuration fragments. Specific routes precede proxy.
RULESETS = (
    ("RednoteReject", "REJECT"),
    ("CustomDirect", "DIRECT"),
    ("CustomAd", "REJECT"),
    ("CustomDownload", "Ⓜ️ 微软云盘"),
    ("CustomJapan", "📲 电报消息"),
    ("CustomUS3", "📢 谷歌FCM"),
    ("CustomProxy", "🚀 节点选择"),
)
QX_TYPES = {
    "DOMAIN": "host",
    "DOMAIN-SUFFIX": "host-suffix",
    "DOMAIN-KEYWORD": "host-keyword",
    "DOMAIN-WILDCARD": "host-wildcard",
}
LOON_XHS_RULE = "DOMAIN-WILDCARD,ads-*.xhscdn.com"
LOON_XHS_HOSTS = (
    "ads-img-al.xhscdn.com",
    "ads-img-qc.xhscdn.com",
    "ads-video-al.xhscdn.com",
    "ads-video-qc.xhscdn.com",
    "ads-vp5.xhscdn.com",
)
LOON_LIMITATION = (
    "Loon 的 RednoteReject 仅保留已列出的 5 个 ads-* 精确域名；"
    "未输出 ads-*.xhscdn.com 通配符，未知广告域名不在此覆盖范围。"
)


def is_rule(line):
    return bool(line) and not line.startswith(("#", ";", "//"))


def read_source(path):
    """Reject unsupported input rather than silently dropping or widening rules."""
    lines = []
    seen = set()
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if is_rule(line):
            fields = [field.strip() for field in line.split(",")]
            error = None
            if len(fields) != 2:
                error = "规则必须只有类型和匹配值两列，不得带策略或额外参数"
            elif fields[0] not in QX_TYPES:
                error = f"尚未支持的规则类型：{fields[0]}"
            else:
                kind, value = fields
                pattern = r"[A-Za-z0-9_.*?-]+" if kind == "DOMAIN-WILDCARD" else r"[A-Za-z0-9_.-]+"
                if not re.fullmatch(pattern, value) or value.startswith(".") or value.endswith(".") or ".." in value:
                    error = f"无效的匹配值：{value!r}"
                elif kind == "DOMAIN-WILDCARD" and not any(char in value for char in "*?"):
                    error = "DOMAIN-WILDCARD 必须包含 * 或 ?"
            if error:
                raise ValueError(f"{path.name}:{number}: {error}")
            line = ",".join(fields)
            if line in seen:
                raise ValueError(f"{path.name}:{number}: 重复规则：{line}")
            seen.add(line)
        lines.append(line)
    if not seen:
        raise ValueError(f"{path.name}: 规则集为空")
    return lines


def qx_policy(policy):
    return policy.lower() if policy in ("DIRECT", "REJECT") else policy


def render_rules(client, name, policy, lines):
    output = [
        "# 自动生成，请勿直接编辑；运行 python3 scripts/build_rules.py 更新。",
        f"# 规则来源：source/{name}.list",
        "",
    ]
    if client == "stash":
        output.append("payload:")
    for line in lines:
        if not is_rule(line):
            # YAML only accepts # comments, while list files also allow ; and //.
            output.append("# " + line.lstrip("/;").strip() if line.startswith((";", "//")) else line)
            continue
        kind, value = line.split(",")
        if client == "loon" and kind == "DOMAIN-WILDCARD":
            # Loon documents no equivalent domain wildcard. This sole, explicit
            # exception keeps the existing exact hosts; it is not an equivalence.
            if name != "RednoteReject" or line != LOON_XHS_RULE:
                raise ValueError(f"{name}: Loon 无法转换通配符：{line}，需明确制定适配方式")
            if not all(f"DOMAIN,{host}" in lines for host in LOON_XHS_HOSTS):
                raise ValueError(f"{name}: Loon 适配所需的 5 个精确广告域名不完整")
            output.append(f"# {LOON_LIMITATION}")
        elif client == "quantumult-x":
            output.append(f"{QX_TYPES[kind]},{value},{qx_policy(policy)}")
        elif client == "stash":
            output.append("  - " + json.dumps(line, ensure_ascii=False))
        else:
            output.append(line)
    return "\n".join(output).rstrip() + "\n"


def render_config(client, base_url):
    output = [
        "# 自动生成的接入片段，不是完整主配置。",
        "# 将策略名改为此 App 已有的策略组；按 README 合并到现有配置。",
        "# 发布到远程仓库后，下列 URL 才能获取本次生成的规则。",
        "",
    ]
    if client == "surge":
        output.extend(["# 合并到现有 [Rule] 顶部，保留原有 FINAL。", "[Rule]"])
    elif client == "loon":
        output.extend([
            "# 合并到现有 [Remote Rule] 前部；本地/插件规则的优先级高于订阅。",
            f"# {LOON_LIMITATION}",
            "[Remote Rule]",
        ])
    elif client == "quantumult-x":
        output.extend([
            "# 合并到现有 [filter_remote]；force-policy 覆盖规则文件中的策略。",
            "[filter_remote]",
        ])
    else:
        output.extend([
            "# 合并 rule-providers；将下面的 rules 条目插入现有 rules 顶部。",
            "# 保留原有 MATCH；不要在同一 YAML 中重复顶层键。",
            "rule-providers:",
        ])
    for name, policy in RULESETS:
        extension = "yaml" if client == "stash" else "list"
        url = f"{base_url}/rules/{client}/{name}.{extension}"
        if client == "surge":
            output.append(f"RULE-SET,{url},{policy}")
        elif client == "loon":
            output.append(f"{url}, policy={policy}, tag={name}, enabled=true")
        elif client == "quantumult-x":
            output.append(
                f"{url}, tag={name}, force-policy={qx_policy(policy)}, "
                "update-interval=86400, opt-parser=false, enabled=true"
            )
        else:
            output.extend([
                f"  {name}:",
                "    behavior: classical",
                "    format: yaml",
                f"    url: {url}",
                "    interval: 86400",
            ])
    if client == "stash":
        output.extend(["", "rules:"])
        output.extend("  - " + json.dumps(f"RULE-SET,{name},{policy}", ensure_ascii=False) for name, policy in RULESETS)
    return "\n".join(output) + "\n"


def build_outputs(root, base_url=BASE_URL):
    base_url = base_url.rstrip("/")
    parts = urlsplit(base_url)
    if (
        parts.scheme != "https" or not parts.hostname or parts.username is not None
        or parts.password is not None or parts.query or parts.fragment
        or re.search(r"[\s,]", base_url)
    ):
        raise ValueError("base-url 必须是无凭据、无查询参数、无逗号和空白的 HTTPS 目录地址")
    expected_sources = {f"{name}.list" for name, _ in RULESETS}
    actual_sources = {path.name for path in (root / "source").glob("*.list")}
    if expected_sources != actual_sources:
        raise ValueError(
            f"source 文件与 RULESETS 不一致；缺少 {sorted(expected_sources - actual_sources)}，"
            f"未登记 {sorted(actual_sources - expected_sources)}"
        )
    sources = {name: read_source(root / "source" / f"{name}.list") for name, _ in RULESETS}
    outputs = {}
    for client in CLIENTS:
        extension = "yaml" if client == "stash" else "list"
        for name, policy in RULESETS:
            path = Path("rules") / client / f"{name}.{extension}"
            outputs[path] = render_rules(client, name, policy, sources[name])
        config_extension = "yaml" if client == "stash" else "conf"
        outputs[Path("config") / f"{client}.{config_extension}"] = render_config(client, base_url)
    return outputs


def main(argv=None, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="检查产物是否同步，不写文件")
    parser.add_argument("--base-url", default=BASE_URL, help="规则发布目录的 HTTPS 地址")
    args = parser.parse_args(argv)
    try:
        outputs = build_outputs(root, args.base_url)
        # Never silently leave obsolete subscriptions behind or delete user files.
        existing = {
            path.relative_to(root)
            for directory in (root / "rules", root / "config")
            for path in directory.rglob("*")
            if path.is_file() and path.suffix in (".list", ".yaml", ".conf")
        }
        if existing - outputs.keys():
            raise ValueError(f"输出目录存在未登记文件，请核对：{sorted(map(str, existing - outputs.keys()))}")
        stale = [
            path for path, content in outputs.items()
            if not (root / path).is_file() or (root / path).read_bytes() != content.encode("utf-8")
        ]
        if args.check and stale:
            print("以下产物缺失或未同步，请运行 python3 scripts/build_rules.py：", file=sys.stderr)
            print("\n".join(map(str, stale)), file=sys.stderr)
            return 1
        if not args.check:
            for path in stale:
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_bytes(outputs[path].encode("utf-8"))
        print(
            f"{'检查通过' if args.check else '生成完成'}："
            f"{len(RULESETS) * len(CLIENTS)} 份规则集、{len(CLIENTS)} 份接入片段。"
        )
        if LOON_XHS_RULE in (root / "source" / "RednoteReject.list").read_text(encoding="utf-8").splitlines():
            print(f"适配差异：{LOON_LIMITATION}")
        return 0
    except (OSError, ValueError) as error:
        print(f"生成失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
