# 狼人杀公平发牌器（开源版）

> 🌐 **在线发牌页**：https://wangzixiao-wzx.github.io/werewolf-dealer/
> 📦 **仓库**：https://github.com/wangzixiao-wzx/werewolf-dealer

一个**零依赖、可审计、可开源**的狼人杀发牌工具。只用 Python 3.8+ 标准库，不需要数据库、不需要服务器、不需要联网，可直接发给朋友或上传到任意代码仓库。网页版 UI 见 `index.html`，双击浏览器打开即可离线使用。

## 核心特性：为什么「公平」且「可信任」

1. **均匀随机，无法被权重算法反推**
   使用 Fisher–Yates 洗牌 + `secrets`（密码学安全随机源）。任何身份 / 座位被抽中的概率严格相等，不引入「老玩家更容易拿狼」「新手保护」之类的可推断结构。

2. **无法被时间戳反推**
   随机源只用系统熵（`secrets` / `os.urandom`），**绝不拿时间当种子**；输出里不带任何时间戳，`deal_id` / `nonce` 也由 `secrets` 生成，无法通过时间重放还原洗牌。

3. **承诺机制（防发牌者事后作弊）**
   - 发牌阶段：只公开 `SHA-256(nonce | 发牌内容)` 的哈希（称为「承诺」），并写入一个**密封文件**。
   - 开牌前：把这段哈希公示给所有人。
   - 开牌阶段：才公开 `nonce` + 最终分配。任何人都能当场复算 `SHA256(nonce | 发牌内容)` 是否等于之前公示的承诺——**若一致，说明发牌者没有在开牌后篡改结果**。

## 文件说明

| 文件 | 作用 |
|------|------|
| `dealer.py` | 核心算法（洗牌 / 解析身份 / 承诺哈希 / 校验），无任何外部依赖 |
| `dealer_standalone.py` | 单文件离线版：内置少量板子预设，可直接 `python dealer_standalone.py` 交互使用 |
| `dealer_cli.py` | 命令行版：支持按板子名 / 自定义身份 / 座位模式发牌与开牌 |
| `index.html` | **网页版 UI**：双击即用、离线可用，纯前端发牌 + 承诺哈希 + 开牌校验 |
| `boards_data.py` | 内置 67 个板子的身份构成 + 角色阵营映射（从原数据库导出，已展开张数） |

## 环境要求

- Python 3.8 及以上
- **无任何第三方依赖**

## 用法

### 方式一：单文件离线版（交互 / 命令行）

```bash
# 交互模式
python dealer_standalone.py

# 命令行：自定义身份构成
python dealer_standalone.py deal --roles "狼人×4 预言家 女巫 猎人 白痴 村民×4" --players 阿泽 小柯 老王 豆豆 大熊 圆圆

# 命令行：用内置板子预设
python dealer_standalone.py deal --board "12人标准场" --players a b c d e f g h i j k l

# 命令行：模式② 玩家随机坐固定座位
python dealer_standalone.py deal --seats --seat-roles "狼人 狼人 预言家 女巫 猎人 村民" --players a b c d e f

# 开牌
python dealer_standalone.py reveal ww_deal_xxxxxxxx.json --txt
```

### 方式二：命令行版（dealer_cli.py，板子更全）

```bash
# 按板子名发牌（自动取该板子身份构成）
python dealer_cli.py deal --board "12人 预女猎白" --players 阿泽 小柯 老王 豆豆 大熊 圆圆

# 自定义身份构成（不依赖板子）
python dealer_cli.py deal --roles "狼人×4 预言家 女巫 猎人 白痴 村民×4" --players a b c d e f

# 模式②：玩家随机坐固定座位
python dealer_cli.py deal --seats --seat-roles "狼人 狼人 预言家 女巫 猎人 村民" --players a b c d e f

# 开牌（读密封文件并校验承诺）
python dealer_cli.py reveal ww_deal_xxxxxxxx.json
```

两种模式说明：
- **roles 模式**：角色随机分配给玩家（输出 玩家 → 身份）。
- **seats 模式（模式②）**：座位身份固定，只随机决定谁坐哪（输出 座位 → 玩家(身份)），适合「座位先定、人后抽」的现场。

### 方式三：网页版 UI（index.html，最直观）

直接用浏览器打开 `index.html` 即可（双击文件，或拖进浏览器）。**无需安装、无需联网、离线可用**，板子数据已内置在页面里。

操作流程：
1. 选板子（67 个）或选「自定义身份构成」自己填；
2. 选发牌模式（角色随机分玩家 / 玩家随机坐固定座位）；
3. 填玩家名单（每行一个，人数须等于身份数，右侧会实时提示 `X / Y`）；
4. 点「发牌并公示承诺哈希」→ 页面显示承诺哈希（可一键复制）；
5. 开牌前把哈希发给所有人；点「下载密封文件」保存 `.json`；
6. 点「开牌并校验」→ 显示座位/身份/阵营，并自动校验哈希。

页面底部还有「核对别人的密封文件」：导入 `.json` 会自动复算哈希，用来验证发牌者有没有作弊。

> 网页版与命令行版算法完全一致：同一份 `ww_deal_*.json` 密封文件，既能在网页里校验，也能用 `python dealer_cli.py reveal` 校验。也可以直接把 `index.html` 放到 GitHub Pages 上，变成在线发牌页。

## 发牌 + 开牌 标准流程

1. 发牌：`python dealer_cli.py deal --board "…" --players …`
   → 屏幕打印【承诺哈希】，并生成 `ww_deal_xxxxxx.json` 密封文件。**把哈希发给所有人，密封文件开牌前自己留着别看。**
2. 开牌：`python dealer_cli.py reveal ww_deal_xxxxxx.json`
   → 打印分配结果并自动校验承诺。所有人复核 `SHA256(nonce | 发牌内容) == 承诺哈希` 即可确认未被篡改。

## 开源 / 二次开发

- 本仓库以 MIT 许可证发布，可自由使用、修改、再分发。
- 想加板子：直接编辑 `boards_data.py` 里的 `BOARDS`（板子名 → 身份名列表）与 `ROLE_FACTION`（角色 → 阵营）即可，`dealer_cli.py` 的 `--board` 会自动识别。
- 想加功能（如更多发牌模式、导出图片）：核心逻辑都在 `dealer.py`，可安全复用。
