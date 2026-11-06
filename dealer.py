# -*- coding: utf-8 -*-
"""公平发牌器核心。

设计原则（用户硬性要求）：
1) 不能用权重算法反推 —— 只做均匀随机（Fisher–Yates），任何身份/座位被抽中的概率严格相等，
   不引入「老玩家更容易拿狼」「新手保护」之类的可推断结构。
2) 不能被时间戳反推 —— 随机数源只用系统熵（secrets / os.urandom），绝不拿时间当种子；
   输出里不带任何时间戳，deal_id / nonce 也由 secrets 生成，无法通过时间重放还原洗牌。

另外提供「承诺机制」：先公开 sha256(nonce || 发牌内容) 的哈希，开牌后再公开 nonce + 分配，
任何人都能当场校验「现在看到的分配」就是「开牌前公示的那个」，发牌者无法事后再改。

本模块不依赖数据库，方便被 server.py 与 dealer_cli.py 共用。
"""
import hashlib
import re
import secrets

# 分隔符：空格 / 逗号（含全角）/ 顿号
_SPLIT = re.compile(r"[\s,，、]+")


def shuffle(seq):
    """均匀 Fisher–Yates 洗牌，使用密码学安全随机源（绝不依赖时间）。"""
    a = list(seq)
    n = len(a)
    for i in range(n - 1, 0, -1):
        j = secrets.randbelow(i + 1)      # [0, i] 均匀
        a[i], a[j] = a[j], a[i]
    return a


def _split_count(tok):
    """把 "狼人×4" / "4×狼人" / "狼人4" / "4狼人" 拆成 (名字, 张数)。"""
    tok = tok.strip()
    m = re.match(r"^(.*?)[×xX]\s*(\d+)$", tok)          # 狼人×4
    if m:
        return m.group(1).strip(), int(m.group(2))
    m = re.match(r"^(\d+)\s*[×xX]\s*(.+)$", tok)        # 4×狼人
    if m:
        return m.group(2).strip(), int(m.group(1))
    m = re.match(r"^(.+?)(\d+)$", tok)                  # 狼人4（后缀数字）
    if m:
        return m.group(1).strip(), int(m.group(2))
    m = re.match(r"^(\d+)(.+)$", tok)                   # 4狼人（前缀数字）
    if m:
        return m.group(2).strip(), int(m.group(1))
    return tok, 1


def parse_roles_text(text):
    """解析「狼人×4 预言家 女巫 村民×3」这类文本 → 有序身份名列表（已展开张数）。"""
    out = []
    for tok in _SPLIT.split((text or "").strip()):
        tok = tok.strip()
        if not tok:
            continue
        name, cnt = _split_count(tok)
        if not name:
            continue
        cnt = max(1, int(cnt))
        out.extend([name] * cnt)
    return out


def deal(players, slots, mode):
    """发牌。

    players : list[str]           玩家名（会去空）
    slots   : list[str]           身份名（角色多重集；seats 模式下按给定顺序视为座位 1..n）
    mode    : "roles" | "seats"
              roles —— 角色随机分玩家（输出 玩家→身份）
              seats —— 玩家随机坐固定座位（座位身份固定，只随机谁坐哪，输出 座位→玩家(身份)）

    返回 (assignment, canonical)：
      assignment : list[dict]  （roles: {player,role}; seats: {seat,player,role}）
      canonical  : str         用于承诺哈希的规范化字符串（不含 nonce）
    """
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
        raise ValueError(
            "玩家数(%d)与身份/座位数(%d)不一致：请让玩家数等于身份数"
            % (len(players), len(slots)))
    if len(set(players)) != len(players):
        # 允许重名但提示（同一名字出现多次时洗牌仍均匀，只是结果有歧义）
        pass
    # 均匀随机：只洗玩家，按 slots 顺序对应。seats 模式下 slots 已是座位顺序。
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
    """把「名单 + 身份构成 + 分配」规范化为确定性字符串，供承诺哈希使用。

    任何人拿到 名单(公开) + 身份构成(公开) + mode + 开牌后的 assignment + nonce，
    都能独立复算出同样的 canonical，从而校验 commit 是否匹配。
    """
    lines = [mode]
    lines.append("\n".join(sorted(players)))          # 名单（排序，消除顺序差异）
    lines.append("---")
    lines.append("\n".join(slots))                     # 身份构成 / 座位布局
    lines.append("---")
    if mode == "seats":
        a = sorted(assignment, key=lambda x: x["seat"])
        lines.append("\n".join("%d\t%s\t%s" % (x["seat"], x["player"], x["role"])
                               for x in a))
    else:
        a = sorted(assignment, key=lambda x: x["player"])
        lines.append("\n".join("%s\t%s" % (x["player"], x["role"]) for x in a))
    return "\n".join(lines)


def commit_of(nonce, canonical):
    """承诺哈希 = SHA256(nonce || "|" || canonical)。"""
    return hashlib.sha256((nonce + "|" + canonical).encode("utf-8")).hexdigest()


def new_nonce():
    """生成不可推测的随机 nonce（来自系统熵，非时间）。"""
    return secrets.token_hex(16)


def verify(nonce, canonical, commit):
    """校验 nonce+canonical 是否与公示的 commit 一致。"""
    return commit_of(nonce, canonical) == commit


if __name__ == "__main__":
    # 简单自检：两种模式各跑一次，打印承诺与开牌。
    import json
    players = ["阿泽", "小柯", "老王", "豆豆", "大熊", "圆圆"]
    slots = ["狼人", "狼人", "预言家", "女巫", "猎人", "村民"]
    for mode in ("roles", "seats"):
        a, canon = deal(players, slots, mode)
        nonce = new_nonce()
        commit = commit_of(nonce, canon)
        print("mode=%s commit=%s verify=%s" % (mode, commit, verify(nonce, canon, commit)))
        print(json.dumps(a, ensure_ascii=False))
