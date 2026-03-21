# 开发规范指南 (Development Guidelines)

为了确保代码质量、可维护性和团队协作效率，本项目制定以下开发规范。

## 1. 代码风格规范 (Code Style)

### 1.1 后端 (Python)
*   **基准**: 遵循 PEP 8 标准。
*   **工具**: 使用 `black` 格式化，`isort` 排序 import。
*   **类型提示**: 所有函数签名必须包含 Type Hints。
    ```python
    def calculate(count: int) -> float: ...
    ```
*   **命名**: Python 变量/函数使用 `snake_case`，类名使用 `PascalCase`。

### 1.2 前端 (Vue 3 + TypeScript)
*   **基准**: Vue 3 风格指南 (A/B级优先)。
*   **组件**: 必须使用 `<script setup lang="ts">`。
*   **工具**: 使用 Prettier + ESLint。
*   **命名**: 组件名 `PascalCase` (如 `UserLogin.vue`)，Props `camelCase`。

## 2. Git 工作流
*   **分支**: 
    - `main`: 生产环境
    - `develop`: 开发主分支
    - `feature/name`: 功能分支
*   **Commit 格式**: `<type>(<scope>): <subject>`
    - 示例: `feat(auth): add jwt login`

## 3. 数据库规范
*   **表名**: 复数 `snake_case` (如 `users`)。
*   **字段**: `is_` 前缀表示布尔值。
*   **变更**: 必须使用 Alembic 迁移脚本。

## 4. API 设计 (RESTful)
*   HTTP Method: GET/POST/PUT/DELETE 语义明确。
*   响应结构统一:
    ```json
    { "success": true, "data": { ... } }
    { "success": false, "error": { "code": "ERR", "message": "msg" } }
    ```

## 5. 测试要求
*   后端核心逻辑覆盖率 > 90%。
*   提交前必须通过 `pytest`。

## 6. 安全与配置
*   敏感信息 (Token/Password) 必须放 `.env`，严禁硬编码。
*   生产环境禁止使用 `print`，必须使用日志库。
