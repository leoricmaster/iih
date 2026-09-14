"""IIH CLI 入口（doc-08 #4 部署运维不进 UI）：stdlib argparse，子命令分发。

子命令：
- ir-create --name ... --spec ...       情报需求登记（落账 Draft）
- ir-activate <id>                       情报需求激活（Draft → Active）
- collect                                自动拉取：Director→fetcher→Collector→executor

无 [project.scripts] 注册；通过 `python -m iih.cli` 调用。
"""

import argparse
import sys
from collections.abc import Sequence

from iih.cli.collect import run as run_collect
from iih.cli.ir import ir_activate, ir_create


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="iih", description="IIH 智能情报中心 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ir_create = sub.add_parser("ir-create", help="情报需求登记")
    p_ir_create.add_argument("--name", required=True, help="需求名称")
    p_ir_create.add_argument(
        "--spec", required=True, help="内容规格（主题、关键词、信源偏好、时效）"
    )
    p_ir_create.set_defaults(func=ir_create)

    p_ir_activate = sub.add_parser("ir-activate", help="情报需求激活")
    p_ir_activate.add_argument("requirement_id", type=int, help="需求 ID")
    p_ir_activate.set_defaults(func=ir_activate)

    p_collect = sub.add_parser("collect", help="自动拉取互联网信源")
    p_collect.set_defaults(func=run_collect)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
