# -*- coding: utf-8 -*-
"""哦~土豆~~ —— 妙妙工具一键启动菜单
把本文件放在和其他脚本同一个文件夹（神秘妙妙工具）里，双击或 python 运行即可。
"""
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 菜单：编号 -> (显示名称, 脚本文件名)
TOOLS = {
    "1": ("签到", "att.py"),
    "2": ("看公告", "spectrum_announcements.py"),
    "3": ("查ddl", "moodle_deadlines.py"),
    "4": ("下载课程资料", "spectrum_download.py"),
    "5": ("更新notebook", "notebooklm_pipeline.py"),
}

# 让 Windows 控制台支持颜色 / UTF-8
os.system("")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

CYAN, GREEN, YELLOW, RED, RESET = "\033[96m", "\033[92m", "\033[93m", "\033[91m", "\033[0m"


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def show_menu():
    clear()
    print(f"{CYAN}=" * 36 + RESET)
    print(f"{CYAN}        哦~土豆~~  妙妙工具箱{RESET}")
    print(f"{CYAN}=" * 36 + RESET)
    print("请选择您的妙妙工具：")
    for key, (name, _) in TOOLS.items():
        print(f"  {GREEN}{key}{RESET}. {name}")
    print(f"  {YELLOW}0{RESET}. 退出")
    print()


def run_tool(key):
    name, script = TOOLS[key]
    path = os.path.join(BASE_DIR, script)
    if not os.path.exists(path):
        print(f"{RED}找不到脚本：{script}（请确认它和本脚本在同一文件夹）{RESET}")
        return
    print(f"\n{CYAN}>>> 正在运行【{name}】...{RESET}\n")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"  # 防止子脚本输出中文乱码
    try:
        # cwd 设为脚本所在目录，这样脚本里读 token.txt / .att.json 之类的相对路径不会出错
        subprocess.run([sys.executable, path], cwd=BASE_DIR, env=env)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}已中断。{RESET}")
    except Exception as e:
        print(f"{RED}运行出错：{e}{RESET}")


def main():
    while True:
        show_menu()
        try:
            choice = input("请输入编号：").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if choice in ("0", "q", "Q"):
            break
        if choice in TOOLS:
            run_tool(choice)
            input(f"\n{GREEN}运行结束，按回车返回菜单...{RESET}")
        else:
            input(f"{RED}无效选择，按回车重新输入...{RESET}")
    print("拜拜，好好学习哦~ 🥔")


if __name__ == "__main__":
    main()
