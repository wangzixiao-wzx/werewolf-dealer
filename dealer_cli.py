# -*- coding: utf-8 -*-
"""发牌器 · 独立命令行版本（与网页端、单文件版共用 dealer.py，算法完全一致）。

本文件为「开源版」：板子数据内置在 boards_data.py 中，不依赖任何数据库 / 服务器 / 第三方库，
仅需 Python 3.8+ 标准库即可运行，可直接发给朋友或上传到代码仓库。

用法：
  # 按板子名发牌（自动取该板子身份构成）
  python dealer_cli.py deal --board "12人 预女猎白" --players 阿泽 小柯 老王 豆豆 大熊 圆圆

  # 自定义身份构成（不依赖板子）
  python dealer_cli.py deal --roles "狼人×4 预言家 女巫 猎人 白痴 村民×4" --players a b c d e f

  # 模式②：玩家随机坐固定座位（指定座位布局）
  python dealer_cli.py deal --seats --seat-roles "狼人 狼人 预言家 女巫 猎人 村民" --players a b c d e f

  # 开牌（读密封文件）
  python dealer_cli.py reveal ww_deal_xxxxxxxx.json

承诺机制：deal 阶段只把 SHA-256 哈希（承诺）打印出来并写入密封文件，开牌前把哈希公示给所有人；
reveal 阶段才公开分配与 nonce，任何人都能当场校验「看到的分配 == 公示的承诺」，发牌者无法事后篡改。
全程使用系统熵随机源（不靠时间），输出不含任何时间戳。
"""
import argparse
import json
import os
import sys

import dealer as DL
import boards_data as BD

SEAL_PREFIX = "ww_deal_"


def _board_slots(board_name):
    norm = lambda s: "".join(s.split())
    target = norm(board_name)
    # 精确匹配
    for name, slots in BD.BOARDS.items():
        if norm(name) == target:
            return name, list(slots)
    # 包含匹配
    for name, slots in BD.BOARDS.items():
        if target in norm(name):
            return name, list(slots)
    sys.exit("找不到板子：%s（可用板子见 boards_data.py 的 BOARDS）" % board_name)


def _role_faction():
    return dict(BD.ROLE_FACTION)


def cmd_deal(args):
    mode = "seats" if args.seats else "roles"
    if args.board:
        bname, slots = _board_slots(args.board)
        src = "板子「%s」" % bname
    elif args.roles:
        slots = DL.parse_roles_text(args.roles)
        src = "自定义身份"
    elif args.seat_roles:
        slots = DL.parse_roles_text(args.seat_roles)
        src = "自定义座位布局"
        mode = "seats"
    else:
        sys.exit("请指定 --board 板子名，或 --roles 自定义身份构成（模式②用 --seat-roles）")
    players = [p.strip() for p in args.players if p.strip()]
    if not players:
        sys.exit("请用 --players 至少提供一个玩家名")
    if len(players) != len(slots):
        sys.exit("玩家数(%d)与身份数(%d)不一致" % (len(players), len(slots)))

    assignment, canonical = DL.deal(players, slots, mode)
    nonce = DL.new_nonce()
    commit = DL.commit_of(nonce, canonical)
    deal_id = nonce[:8]
    seal = {"deal_id": deal_id, "mode": mode, "players": players, "slots": slots,
            "assignment": assignment, "nonce": nonce, "commit": commit}
    path = os.path.join(os.getcwd(), SEAL_PREFIX + deal_id + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(seal, f, ensure_ascii=False, indent=2)

    print("来源：%s" % src)
    print("模式：%s" % ("玩家随机坐固定座位" if mode == "seats" else "角色随机分玩家"))
    print("玩家数：%d" % len(players))
    print()
    print("【承诺哈希 SHA-256】—— 开牌前把这段发给所有人：")
    print("  " + commit)
    print()
    print("密封文件（开牌前勿看）：%s" % path)
    print("开牌命令：python dealer_cli.py reveal %s" % path)


def cmd_reveal(args):
    if not os.path.exists(args.file):
        sys.exit("找不到密封文件：%s" % args.file)
    with open(args.file, "r", encoding="utf-8") as f:
        seal = json.load(f)
    canonical = DL._canonical(seal["players"], seal["slots"], seal["mode"], seal["assignment"])
    ok = DL.verify(seal["nonce"], canonical, seal["commit"])
    fac = _role_faction()
    mode_txt = "玩家随机坐固定座位" if seal["mode"] == "seats" else "角色随机分玩家"
    lines = ["【狼人杀发牌结果】", "模式：" + mode_txt,
             "承诺哈希 SHA-256：" + seal["commit"],
             "校验：" + ("✓ 通过（与公示承诺一致，未被篡改）" if ok else "✗ 失败"),
             "",
             (head := "座位\t玩家\t身份\t阵营" if seal["mode"] == "seats" else "玩家\t身份\t阵营")]
    for a in seal["assignment"]:
        if seal["mode"] == "seats":
            lines.append("%d\t%s\t%s\t%s" % (a["seat"], a["player"], a["role"], fac.get(a["role"], "")))
        else:
            lines.append("%s\t%s\t%s" % (a["player"], a["role"], fac.get(a["role"], "")))
    lines.append("")
    lines.append("开牌前请公示该哈希；任何人可复核 SHA256(nonce | 发牌内容) == 承诺，发牌者无法事后篡改。")
    text = "\n".join(lines)

    print(text)
    if not ok:
        sys.exit(1)
    if args.txt:
        path = args.txt if args.txt != "1" else (os.path.splitext(args.file)[0] + ".txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print("\n已导出分享文本：%s" % path)


def main():
    ap = argparse.ArgumentParser(description="狼人杀公平发牌器（均匀随机 + 承诺哈希）")
    sub = ap.add_subparsers(dest="cmd")

    d = sub.add_parser("deal", help="发牌并生成承诺哈希")
    d.add_argument("--board", help="板子名（自动取身份构成，见 boards_data.py）")
    d.add_argument("--roles", help="自定义身份构成，如 '狼人×4 预言家 女巫 猎人 白痴 村民×4'")
    d.add_argument("--seat-roles", help="模式②座位布局，如 '狼人 狼人 预言家 ...'")
    d.add_argument("--seats", action="store_true", help="模式②：玩家随机坐固定座位")
    d.add_argument("--players", nargs="+", required=True, help="玩家名（空格分隔）")
    d.set_defaults(func=cmd_deal)

    r = sub.add_parser("reveal", help="开牌（读密封文件并校验）")
    r.add_argument("file", help="密封文件路径（ww_deal_*.json）")
    r.add_argument("--txt", nargs="?", const="1", help="同时导出分享文本（可接文件名，省略则同名 .txt）")
    r.set_defaults(func=cmd_reveal)

    args = ap.parse_args()
    if not getattr(args, "cmd", None):
        ap.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
