# AgentsChat
Agent们的聊天群，他们会创造些什么？
## 目录结构说明

### agents/
- **agent.py** - 核心 Agent 实现
- **controller.py** - LLM 输出到 Agent 行为的转换层
- **policies.py** - Agent 行为约束和策略

### platform/
- **world.py** - 世界状态管理和事件可见性
- **router.py** - 事件分发和路由规则
- **observers.py** - UI / Logger / Agent观察者模式接口实现

### events/
- **types.py** - 事件类型定义和协议
- **store.py** - 事件存储接口
- **query.py** - 历史事件检索接口

### llm/
- **client.py** - LLM API 客户端封装
- **prompts.py** - Prompt 模板管理
- **schemas.py** - LLM 输出结构化定义

### runtime/
- **loop.py** - 事件驱动的主循环
- **scheduler.py** - 发言和行动调度器

### ui/
- **console.py** - 控制台界面实现

### config/
- **settings.py** - 全局配置管理

### 根目录文件
- **main.py** - 程序入口点
- **README.md** - 项目说明文档