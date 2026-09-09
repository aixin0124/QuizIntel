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
│   ├── storage/                # SQLite 数据库
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
LLM_WIRE_API=responses
LLM_REASONING_EFFORT=low
```

项目运行时始终调用真实大模型 API。`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` 任意一项为空或仍为占位文字时，启动脚本会停止并提示配置错误。

支持以下协议：

- `LLM_WIRE_API=responses`
- `LLM_WIRE_API=chat_completions`

`.env` 已被 `.gitignore` 忽略，不要把真实密钥提交到 Git 仓库。如果密钥曾经出现在公开仓库或聊天记录中，应先轮换密钥再继续使用。

## Windows 一键启动

双击项目根目录的 `start.bat`。

脚本会自动：

1. 创建 `.venv` Python 虚拟环境。
2. 安装 `backend/requirements.txt` 中的后端依赖。
3. 使用 `frontend/package-lock.json` 安装前端依赖。
4. 检查 `.env` 中的大模型配置。
5. 启动后端和前端进程，并等待两个服务就绪。

启动后访问：

- 用户端：http://localhost:5173
- 后端健康检查：http://localhost:8000/api/health

依赖需要重新安装时，在项目根目录执行：

```powershell
.\start.ps1 -Install
```

## 手动启动

后端：

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

## 答辩操作流程

1. 启动项目并打开用户端。
2. 点击“管理后台”，使用 `.env` 中的 `ADMIN_PASSWORD` 登录，默认值为 `10124`。
3. 进入“创建包装”，使用示例问卷或上传 CSV/JSON。
4. 点击“解析问卷”。
5. 填写调研目标和互动主题，点击“生成互动包装”。
6. 后端调用真实大模型 API 生成包装内容。
7. 切换到用户端完成答题。
8. 回到管理后台查看题目映射、统计结果，并导出 Excel 或 PDF。

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

- 导入 CSV 或 JSON 问卷
- 识别题目、题型、选项和研究标签
- 调用 OpenAI 兼容大模型生成互动包装
- 通过 `question_id` 保留原始题目和互动题面的映射
- 在线答题并生成趣味结果
- SQLite 保存包装方案和匿名答卷
- 查看结果分布、研究选项分布和答卷数量
- 导出 Excel 明细和 PDF 调研报告

## 毕业答辩技术说明

系统可以概括为“React + Vite 前端、FastAPI 后端、SQLite 数据库、OpenAI 兼容大模型服务”的前后端分离应用。

大模型负责生成主题、文案和互动题面；系统会强制保留原始题目编号、研究标签和研究选项，避免包装内容影响后续研究数据统计。答卷提交、结果计算、数据持久化和报表导出由后端完成。

互动结果仅用于轻量娱乐展示，不应表述为心理诊断、医学结论或科学人格测量。
