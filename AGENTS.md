# 仓库协作指导

本文件适用于整个 `SkillOpt` 仓库。后续在本仓库内修改代码、编写文档、运行脚本或生成说明时，请遵循以下约定。

## Markdown 输出

- 所有新增或修改的 Markdown 文档、实验说明、运行记录、总结报告和面向用户的说明文字，默认使用中文输出。
- 必须保留上游项目已有的英文专有名词、API 名称、命令、路径、配置键和论文标题，不要为了中文化而改写会影响检索或执行的标识符。
- 在 Windows 环境下编辑 Markdown 时，统一保存为 UTF-8 编码，避免 GBK、ANSI 或终端默认编码导致中文乱码。
- 如果需要在 PowerShell 中查看或生成中文 Markdown，优先设置 UTF-8 输出：

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
```

## Python 入口脚本

- 新增或改造 `scripts/` 下的 Python 入口脚本时，必须同时支持命令行传参和脚本内传参，方便在终端与 IDE 中直接运行。
- 推荐入口结构如下：

```python
from __future__ import annotations

import argparse
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    run(args)


if __name__ == "__main__":
    SCRIPT_ARGS: list[str] = [
        "--config",
        "configs/searchqa/default.yaml",
    ]

    main()
    # IDE 直接运行且需要默认参数时，可临时改为：
    # main(SCRIPT_ARGS)
```

- `main(argv=None)` 应作为稳定入口：`None` 表示读取真实命令行参数，传入列表表示使用脚本内或测试中指定的参数。
- 不要把实验参数硬编码在业务逻辑内部；如需脚本内默认值，集中放在 `if __name__ == "__main__":` 下方的 `SCRIPT_ARGS` 或同类常量中，并保持命令行参数仍然可覆盖。
- 入口脚本应尽量只负责解析参数和调用核心函数，核心逻辑放入可复用函数，便于测试和二次调用。

## Python 运行环境

- 需要运行 Python 文件、测试、训练、评估或数据处理脚本时，先激活 `llm` conda 虚拟环境。
- Windows PowerShell 推荐命令：

```powershell
conda activate llm
python scripts/train.py --help
```

- 如果当前终端无法保持 conda 激活状态，可使用：

```powershell
conda run -n llm python scripts/train.py --help
```

- 运行前确认依赖安装在 `llm` 环境中；不要把依赖安装到系统 Python 或其他无关环境。

## 修改与验证

- 修改代码前先阅读相邻模块和现有调用方式，优先沿用本仓库已有风格。
- 文档或脚本中涉及文件读写时，显式指定 `encoding="utf-8"`。
- 涉及 Windows 控制台输出的 Python 脚本，应避免依赖系统默认编码；必要时设置 `PYTHONUTF8=1` 或 `PYTHONIOENCODING=utf-8`。
- 完成代码修改后，优先在 `llm` 环境中运行最小必要验证命令，并在结果说明中用中文概述验证情况。
