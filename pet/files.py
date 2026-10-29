"""写文件的小工具。"""
from __future__ import annotations

import json
import os


def write_json_atomic(path: str, data) -> None:
    """先写到 .tmp 再替换：写到一半出错（或程序被关掉），原来的文件还是完整的。"""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
