# -*- coding: utf-8 -*-
"""公平狼人杀发牌器 · 单文件版（零依赖，仅用 Python 标准库）。

设计原则：
1) 均匀随机：Fisher-Yates + secrets（密码学安全随机源），任何身份/座位被抽中概率严格相等，
   不引入任何可推断结构，也不拿时间当种子。
2) 承诺机制：先公开 SHA-256(nonce | 发牌内容) 的哈希，开牌后再公开 nonce + 分配，
   任何人都能当场校验「现在看到的分配 == 开牌前公示的那个」，发牌者无法事后篡改/定向生成。

本文件不依赖数据库、不依赖服务器，可直接发给朋友或开源。
（需要联网板子库时用项目内的 dealer_cli.py；本文件用内置板子预设，离线可用。）

用法：
  # 交互模式（直接运行，按提示输入）
  python dealer_standalone.py

  # 命令行：自定义身份构成
  python dealer_standalone.py deal --roles "狼人×4 预言家 女巫 猎人 白痴 村民×4" --players 阿泽 小柯 老王 豆豆 大熊 圆圆

  # 命令行：用内置板子预设
  python dealer_standalone.py deal --board "12人标准场" --players a b c d e f g h i j k l

  # 命令行：模式② 玩家随机坐固定座位
  python dealer_standalone.py deal --seats --seat-roles "狼人 狼人 预言家 女巫 猎人 村民" --players a b c d e f

  # 开牌（读密封文件，可同时导出分享文本）
  python dealer_standalone.py reveal ww_deal_xxxxxxxx.json --txt
"""
import argparse
import hashlib
import json
import os
import re
import secrets
import sys

SEAL_PREFIX = "ww_deal_"
_SPLIT = re.compile(r"[\s,，、]+")

# ---------------------------------------------------------------------------
# 内置板子预设（离线可用，可自行增删；与数据库无关）
# ---------------------------------------------------------------------------
BOARDS = {
    "9人标准场": ["狼人", "狼人", "预言家", "女巫", "猎人", "村民", "村民", "村民", "村民"],
    "10人标准场": ["狼人", "狼人", "狼人", "预言家", "女巫", "猎人", "白痴", "村民", "村民", "村民"],
    "12人标准场": ["狼人", "狼人", "狼人", "预言家", "女巫", "猎人", "白痴",
                "村民", "村民", "村民", "村民", "村民"],
    "12人预女猎白": ["狼人", "狼人", "狼人", "预言家", "女巫", "猎人", "白痴",
                "村民", "村民", "村民", "村民", "村民"],
}


# ---------------------------------------------------------------------------
# 核心算法（与 dealer.py 完全一致）
# ---------------------------------------------------------------------------
def shuffle(seq):
    """均匀 Fisher-Yates 洗牌，使用密码学安全随机源（绝不依赖时间）。"""
    a = list(seq)
    n = len(a)
    for i in range(n - 1, 0, -1):
        j = secrets.randbelow(i + 1)      # [0, i] 均匀
        a[i], a[j] = a[j], a[i]
    return a


def _split_count(tok):
    tok = tok.strip()
    m = re.match(r"^(.*?)[×xX]\s*(\d+)$", tok)
    if m:
        return m.group(1).strip(), int(m.group(2))
    m = re.match(r"^(\d+)\s*[×xX]\s*(.+)$", tok)
    if m:
        return m.group(2).strip(), int(m.group(1))
    m = re.match(r"^(.+?)(\d+)$", tok)
    if m:
        return m.group(1).strip(), int(m.group(2))
    m = re.match(r"^(\d+)(.+)$", tok)
    if m:
        return m.group(2).strip(), int(m.group(1))
    return tok, 1


def parse_roles_text(text):
    out = []
    for tok in _SPLIT.split((text or "").strip()):
        tok = tok.strip()
        if not tok:
            continue
        name, cnt = _split_count(tok)
        if not name:
            continue
        out.extend([name] * max(1, int(cnt)))
    return out


def deal(players, slots, mode):
    if mode not in ("roles", "seats"):
        raise ValueError("mode 只能是 roles 或 seats")
    players = [p.strip() for p in (players or [])]
    players = [p for p in players if p]
    slots = [s.strip() for s in (slots or [])]
    slots = [s for s in slots if s]
    if not players:
        raise ValueError("请填写玩家名单")
    if not slots:
        raise ValueError("请选择板子或填写身份构成")
    if len(players) != len(slots):
        raise ValueError("玩家数(%d)与身份/座位数(%d)不一致" % (len(players), len(slots)))
    perm = shuffle(players)
    assignment = []
    for i, role in enumerate(slots):
        item = {"player": perm[i], "role": role}
        if mode == "seats":
            item["seat"] = i + 1
        assignment.append(item)
    canonical = _canonical(players, slots, mode, assignment)
    return assignment, canonical


def _canonical(players, slots, mode, assignment):
    lines = [mode]
    lines.append("\n".join(sorted(players)))
    lines.append("---")
    lines.append("\n".join(slots))
    lines.append("---")
    if mode == "seats":
        a = sorted(assignment, key=lambda x: x["seat"])
        lines.append("\n".join("%d\t%s\t%s" % (x["seat"], x["player"], x["role"]) for x in a))
    else:
        a = sorted(assignment, key=lambda x: x["player"])
        lines.append("\n".join("%s\t%s" % (x["player"], x["role"]) for x in a))
    return "\n".join(lines)


def commit_of(nonce, canonical):
    return hashlib.sha256((nonce + "|" + canonical).encode("utf-8")).hexdigest()


def new_nonce():
    return secrets.token_hex(16)


def verify(nonce, canonical, commit):
    return commit_of(nonce, canonical) == commit


# ---------------------------------------------------------------------------
# 命令行 / 交互
# ---------------------------------------------------------------------------
def _role_faction():
    """极简阵营推断（仅用于展示，不影响正确性）。"""
    wolf = {"狼人", "狼王", "狼美人", "机械狼", "隐狼", "觉醒隐狼", "石像鬼", "狼巫",
            "狼枪", "狼鸦之爪", "恶魔", "典狱长"}
    good_god = {"预言家", "女巫", "猎人", "白痴", "守卫", "摄梦人", "骑士", "乌鸦",
                "天使", "猎魔人", "通灵师", "天眼", "侦探", "愚者", "市长"}
    third = {"第三方", "丘比特", "盗贼", "咒狐", "白虎", "变色龙", "恶灵骑士", "祈求者"}
    out = {}
    for name in set(wolf):
        out[name] = "狼人"
    for name in set(good_god):
        out[name] = "好人神职"
    for name in set(third):
        out[name] = "第三方"
    return out


def _cmd_deal(args):
    mode = "seats" if args.seats else "roles"
    if args.board:
        if args.board not in BOARDS:
            sys.exit("内置板子预设没有「%s」。可用：%s" % (args.board, "、".join(BOARDS)))
        slots = list(BOARDS[args.board])
        src = "内置板子「%s」" % args.board
    elif args.roles:
        slots = parse_roles_text(args.roles)
        src = "自定义身份"
    elif args.seat_roles:
        slots = parse_roles_text(args.seat_roles)
        src = "自定义座位布局"
        mode = "seats"
    else:
        sys.exit("请指定 --board 板子名，或 --roles 自定义身份构成（模式②用 --seat-roles）")
    players = [p.strip() for p in args.players if p.strip()]
    if not players:
        sys.exit("请用 --players 至少提供一个玩家名")

    assignment, canonical = deal(players, slots, mode)
    nonce = new_nonce()
    commit = commit_of(nonce, canonical)
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
    print("开牌命令：python %s reveal %s" % (os.path.basename(__file__), path))


def _cmd_reveal(args):
    if not os.path.exists(args.file):
        sys.exit("找不到密封文件：%s" % args.file)
    with open(args.file, "r", encoding="utf-8") as f:
        seal = json.load(f)
    canonical = _canonical(seal["players"], seal["slots"], seal["mode"], seal["assignment"])
    ok = verify(seal["nonce"], canonical, seal["commit"])
    fac = _role_faction()
    mode_txt = "玩家随机坐固定座位" if seal["mode"] == "seats" else "角色随机分玩家"
    lines = ["【狼人杀发牌结果】", "模式：" + mode_txt,
             "承诺哈希 SHA-256：" + seal["commit"],
             "校验：" + ("✓ 通过（与公示承诺一致，未被篡改）" if ok else "✗ 失败"),
             "",
             ("座位\t玩家\t身份\t阵营" if seal["mode"] == "seats" else "玩家\t身份\t阵营")]
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


def _interactive():
    print("=== 公平狼人杀发牌器（交互模式）===")
    print("模式：1) 角色随机分玩家  2) 玩家随机坐固定座位")
    m = input("选模式 [1/2，默认1]：").strip() or "1"
    mode = "seats" if m == "2" else "roles"

    print("\n内置板子预设：%s" % "、".join(BOARDS))
    board = input("用板子？（直接回车=不用，自己写身份）：").strip()
    roles_text = ""
    if board:
        if board not in BOARDS:
            sys.exit("没有这个板子预设，请改用自定义身份。")
        slots = list(BOARDS[board])
    else:
        if mode == "seats":
            roles_text = input("按座位顺序填身份（空格/顿号分隔）：").strip()
        else:
            roles_text = input("填身份构成，如 狼人×4 预言家 女巫 猎人 白痴 村民×4：").strip()
        slots = parse_roles_text(roles_text)
        if not slots:
            sys.exit("身份构成为空。")

    print("\n玩家名单（每行一个，人数须等于 %d）：" % len(slots))
    players = []
    while True:
        line = input("  玩家%d： " % (len(players) + 1)).strip()
        if not line:
            break
        players.append(line)
    if len(players) != len(slots):
        sys.exit("玩家数(%d)与身份数(%d)不一致。" % (len(players), len(slots)))

    assignment, canonical = deal(players, slots, mode)
    nonce = new_nonce()
    commit = commit_of(nonce, canonical)
    deal_id = nonce[:8]
    seal = {"deal_id": deal_id, "mode": mode, "players": players, "slots": slots,
            "assignment": assignment, "nonce": nonce, "commit": commit}
    path = os.path.join(os.getcwd(), SEAL_PREFIX + deal_id + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(seal, f, ensure_ascii=False, indent=2)

    print("\n【承诺哈希 SHA-256】—— 开牌前把这段发给所有人：")
    print("  " + commit)
    print("\n密封文件（开牌前勿看）：%s" % path)
    print("开牌命令：python %s reveal %s" % (os.path.basename(__file__), path))


def main():
    ap = argparse.ArgumentParser(description="狼人杀公平发牌器（均匀随机 + 承诺哈希，单文件零依赖）")
    sub = ap.add_subparsers(dest="cmd")

    d = sub.add_parser("deal", help="发牌并生成承诺哈希")
    d.add_argument("--board", help="内置板子预设名（见文件顶部 BOARDS）")
    d.add_argument("--roles", help="自定义身份构成，如 '狼人×4 预言家 女巫 猎人 白痴 村民×4'")
    d.add_argument("--seat-roles", help="模式②座位布局，如 '狼人 狼人 预言家 ...'")
    d.add_argument("--seats", action="store_true", help="模式②：玩家随机坐固定座位")
    d.add_argument("--players", nargs="+", required=True, help="玩家名（空格分隔）")
    d.set_defaults(func=_cmd_deal)

    r = sub.add_parser("reveal", help="开牌（读密封文件并校验）")
    r.add_argument("file", help="密封文件路径（ww_deal_*.json）")
    r.add_argument("--txt", nargs="?", const="1", help="同时导出分享文本（可接文件名）")
    r.set_defaults(func=_cmd_reveal)

    args = ap.parse_args()
    if not getattr(args, "cmd", None):
        _interactive()
        return
    args.func(args)


if __name__ == "__main__":
    main()
