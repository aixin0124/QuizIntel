# 趣测智研

基于生成式 AI 的互动式市场调研问卷包装平台。系统将普通问卷转换为带有主题、互动题面和结果反馈的测评，同时保留原始题目编号和研究字段，支持后续统计分析。

## 项目结构

```text
.
├── backend/
│   ├── main.py                 # FastAPI 后端入口和 API 路由
│   ├── config.py               # 后端配置
│   ├── models.py               # 数据模型
│   ├── requirements.txt        # 后端依赖
│   ├── services/               # 问卷、AI、统计业务
│   ├── storage/                # MySQL/SQLite 存储、初始化和迁移脚本
│   ├── utils/                  # Excel、PDF 导出
│   └── tests/                  # 后端测试
├── frontend/
│   ├── src/                    # React 页面
│   ├── package.json            # 前端依赖和命令
│   ├── package-lock.json       # 前端依赖锁定版本
│   └── vite.config.ts          # Vite 开发服务器和 API 代理
├── data/
│   └── .gitkeep                # 数据库运行目录
├── .env.example                # API 配置模板
├── start.bat                   # Windows 双击启动入口
└── start.ps1                   # Windows 启动脚本
```

这是前后端分离结构：

- `frontend` 只负责 React 页面和用户交互。
- `backend` 只负责 FastAPI 接口、业务逻辑、数据库和大模型调用。
- 大模型密钥只由后端读取，前端不会接触。
- 前端通过 Vite 将 `/api` 请求代理到 `http://127.0.0.1:8000`。

## 配置真实大模型 API

复制 `.env.example` 为项目根目录的 `.env`，填写真实配置：

```text
LLM_API_KEY=你的完整密钥
LLM_BASE_URL=https://你的兼容接口地址
LLM_MODEL=你的模型名称
LLM_WIRE_API=chat_completions
LLM_REASONING_EFFORT=low
LLM_MAX_OUTPUT_TOKENS=6000

# 可选：基元律动兜底接口，主接口失败时使用
LLM_FALLBACK_API_KEY=你的基元律动密钥
LLM_FALLBACK_BASE_URL=https://tokenrhythm.studio/v1
LLM_FALLBACK_MODEL=deepseek-v4-flash
```

项目运行时始终调用真实大模型 API。`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` 任意一项为空或仍为占位文字时，启动脚本会停止并提示配置错误。

支持以下协议：

- `LLM_WIRE_API=responses`
- `LLM_WIRE_API=chat_completions`

当前 `.env.example` 按 `https://www.blackaicoding.com` 这类兼容网关配置为 `chat_completions`。这类网关通常使用 `/v1/chat/completions`，项目会在填写根域名时自动补上 `/v1`。如果你使用的服务明确支持 Responses API，再改为 `LLM_WIRE_API=responses`。

如果配置了 `LLM_FALLBACK_API_KEY`，主模型接口调用失败时会自动改用基元律动兜底接口。基元律动按 Chat Completions 协议调用，接口地址为 `https://tokenrhythm.studio/v1/chat/completions`，默认兜底模型为 `deepseek-v4-flash`。

`.env` 已被 `.gitignore` 忽略，不要把真实密钥提交到 Git 仓库。如果密钥曾经出现在公开仓库或聊天记录中，应先轮换密钥再继续使用。

## Windows 启动方式

### 第一次运行：准备环境

打开两个窗口前，先在 `cmd` 中执行一次下面的环境准备命令：

```bat
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd /d ".\frontend"
npm ci
cd /d "../"
```

如果项目根目录还没有 `.env`，先执行：

```bat
copy .env.example .env
notepad .env
```

然后在 `.env` 中填写 `LLM_API_KEY`、`LLM_BASE_URL` 和 `LLM_MODEL`。

### 日常启动

每次启动需要打开两个 `cmd` 窗口。两个窗口都不要关闭，关闭窗口或按 `Ctrl+C` 就会停止对应服务。

窗口一：启动后端，复制下面两行执行：

```bat
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

窗口二：启动前端，复制下面两行执行：

```bat
cd /d ".\frontend"
npm run dev -- --host 127.0.0.1
```

启动成功后访问：

- 用户端：http://localhost:5173
- 后端健康检查：http://localhost:8000/api/health

### 停止项目

优先在运行后端或前端的窗口中按 `Ctrl+C`。如果窗口已经关掉，但服务还在后台，可以在 `cmd` 中按端口查找进程：

```bat
netstat -ano | findstr ":8000"
netstat -ano | findstr ":5173"
```

最后一列是进程编号 PID。把下面的 `<进程编号>` 替换成实际 PID：

```bat
taskkill /PID <进程编号> /T /F
```

例如：

```bat
taskkill /PID 12345 /T /F
```

再次执行下面两条命令确认端口已经释放：

```bat
netstat -ano | findstr ":8000"
netstat -ano | findstr ":5173"
```

没有出现 `LISTENING` 就表示对应服务已经停止。

### 重新安装依赖

后端依赖：

```bat
cd /d "D:\desktop\毕业\趣测智研"
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

前端依赖：

```bat
cd /d "D:\desktop\毕业\趣测智研\frontend"
npm ci
```

如果你的工作区中仍有 `start.bat` 和 `start.ps1`，只建议在明确需要自动启动、并且知道如何用端口命令停止后台进程时使用。

## 答辩操作流程

1. 启动项目并打开管理后台。
2. 打开首页即进入管理后台登录，默认管理员账号为 `admin`，初始密码为 `10124`。
3. 进入“创建包装”，点击“选择推荐问卷模板”，在浮空窗口中选择真实问卷模板并导入；也可以粘贴问卷星公开链接。
4. 确认解析出的题目，可按需要微调题目、选项和题型。
5. 填写调研目标和互动主题，点击“生成互动包装”。
6. 后端调用真实大模型 API 生成包装草稿，管理员先预览题目映射和分享链接。
7. 确认无误后点击发布，问卷进入“收集中”，用户只能通过 `/share/{token}` 分享链接填写。
8. 顶部“用户端”入口会按原用户端样式列出所有已发布问卷，管理员可以浏览和测试；后台浏览答卷默认计入统计，只有明确测试或管理员标记无效的答卷不计入。
9. 回到管理后台查看题目映射、统计结果，并导出 Excel 或 PDF。

## MySQL 初始化与旧数据迁移

本项目现在默认使用本机 MySQL 8：

```text
DATABASE_URL=mysql+pymysql://root:10124@127.0.0.1:3306/fun_research?charset=utf8mb4
```

初始化数据库：

```bat
cd /d "D:\desktop\毕业\趣测智研"
mysql -uroot -p10124 --default-character-set=utf8mb4 < backend\storage\init_mysql.sql
```

安装新依赖后迁移旧 SQLite 数据：

```bat
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m backend.storage.migrate_sqlite_to_mysql --sqlite data\fun_research.db --mysql "mysql+pymysql://root:10124@127.0.0.1:3306/fun_research?charset=utf8mb4"
```

表结构说明见 `backend/storage/SCHEMA.md`。迁移脚本会直接把 SQLite 历史问卷和答卷插入 MySQL，不把业务数据写入初始化 SQL。

## 可行性验证

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

检查前端生产构建：

```powershell
cd frontend
npm run build
```

检查后端健康状态：

```powershell
Invoke-WebRequest http://127.0.0.1:8000/api/health
```

## 主要功能

- 从推荐模板浮窗导入真实公开问卷
- 粘贴问卷星公开转发链接导入题目
- 识别题目、题型、选项和研究标签
- 调用 OpenAI 兼容大模型生成互动包装
- 通过 `question_id` 保留原始题目和互动题面的映射
- 在线答题并生成趣味结果
- MySQL 保存包装方案、匿名答卷、管理员账号、操作日志和 AI 生成记录
- 生成后先保存草稿，管理员预览确认后再发布
- 通过分享链接访问公开答题页，普通用户不能获取问卷列表
- 管理员后台内置“用户端”浏览页，可查看所有已发布问卷并进行测试
- 查看结果分布、研究选项分布和答卷数量
- 导出 Excel 明细和 PDF 调研报告

## 毕业答辩技术说明

系统可以概括为“React + Vite 前端、FastAPI 后端、SQLite 数据库、OpenAI 兼容大模型服务”的前后端分离应用。

大模型负责生成主题、文案和互动题面；系统会强制保留原始题目编号、研究标签和研究选项，避免包装内容影响后续研究数据统计。答卷提交、结果计算、数据持久化和报表导出由后端完成。

互动结果仅用于轻量娱乐展示，不应表述为心理诊断、医学结论或科学人格测量。
